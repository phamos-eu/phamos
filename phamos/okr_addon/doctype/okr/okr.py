# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate, add_days, getdate
from frappe.model.document import Document

class OKR(Document):
    def validate(self):
        self.validate_measurables()
        self.validate_and_update_is_group()

    def get_invalid_links(self, is_submittable=False):
        """Allow parent_kra with value 'metric_name||idx': don't let base validation overwrite it."""
        saved_parent_kra = None
        if self.get("parent_kra") and "||" in str(self.parent_kra):
            saved_parent_kra = self.parent_kra
        invalid_links, cancelled_links = super().get_invalid_links(is_submittable=is_submittable)
        if saved_parent_kra is not None:
            setattr(self, "parent_kra", saved_parent_kra)
        if not invalid_links:
            return invalid_links, cancelled_links
        filtered = []
        for item in invalid_links:
            fieldname, docname, msg = item
            if fieldname == "parent_kra" and docname and "||" in str(docname):
                kr_name, _ = parse_parent_kra(docname)
                if kr_name and frappe.db.exists("KR", kr_name):
                    continue
            filtered.append(item)
        return filtered, cancelled_links

    def before_save(self):
        self.update_measurable_targets()
        # Calculate and update progress based on measurables
        self.progress = self.calculate_progress()
        # Calculate OKR score (0.0-1.0)
        self.okr_score = self.calculate_okr_score()
        # Set next check-in date
        self.set_next_check_in()

    def after_save(self):
        self.update_parent_okr_progress()
        # Update parent OKR's measurables if this OKR is linked via parent_kra
        self.update_parent_measurable_progress()

    def on_trash(self):
        """Handle when OKR is deleted - update parent's is_group and measurable progress if needed"""
        if self.parent_okr:
            # Count children excluding this record (which is about to be deleted)
            remaining_children = frappe.db.count(
                "OKR",
                filters={"parent_okr": self.parent_okr, "name": ["!=", self.name]}
            )

            # If parent will have no children after this deletion, uncheck parent's is_group
            if remaining_children == 0:
                frappe.db.set_value("OKR", self.parent_okr, "is_group", 0, update_modified=False)
                frappe.db.commit()

        # Update parent measurable progress if this OKR was linked via parent_kra
        if self.parent_okr and self.parent_kra:
            try:
                parent = frappe.get_doc("OKR", self.parent_okr)
                metric_name, idx = parse_parent_kra(self.parent_kra)
                if not metric_name:
                    metric_name = self.parent_kra
                for i, measurable in enumerate(parent.measurables or []):
                    if measurable.metric_name != metric_name:
                        continue
                    if idx is not None and i != idx:
                        continue
                    stored_kra = _stored_parent_kra_for_measurable(parent, measurable, i)
                    child_okrs_with_kra = frappe.get_all(
                        "OKR",
                        filters={
                            "parent_okr": self.parent_okr,
                            "parent_kra": stored_kra,
                            "name": ["!=", self.name]
                        },
                        fields=["name", "progress"]
                    )

                    if child_okrs_with_kra:
                        total_measurable_progress = 0
                        valid_measurable_count = 0
                        for child_okr in child_okrs_with_kra:
                            try:
                                child_doc = frappe.get_doc("OKR", child_okr.name)
                                if child_doc.measurables:
                                    for child_measurable in child_doc.measurables:
                                        if child_measurable.percent_complete is not None:
                                            total_measurable_progress += child_measurable.percent_complete
                                            valid_measurable_count += 1
                            except Exception as e:
                                frappe.log_error(f"Error getting child OKR measurables on delete: {str(e)}")
                        if valid_measurable_count > 0:
                            measurable.percent_complete = total_measurable_progress / valid_measurable_count
                        else:
                            measurable.percent_complete = 0
                    else:
                        if measurable.current_value is not None and measurable.committed_target is not None and measurable.baseline_value is not None:
                            baseline_to_target = measurable.committed_target - measurable.baseline_value
                            if baseline_to_target != 0:
                                progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                                measurable.percent_complete = min(max(progress * 100, 0), 100)
                            else:
                                measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                        else:
                            measurable.percent_complete = 0
                    break

                # Save parent to persist the measurable progress update
                parent.save()
            except Exception as e:
                frappe.log_error(f"Error updating parent measurable progress on delete: {str(e)}")

    def calculate_progress(self):
        """Calculate overall progress from measurables"""
        if not self.measurables:
            return 0

        total_percent = 0
        valid_measurables = 0

        for measurable in self.measurables:
            if measurable.percent_complete is not None:
                total_percent += measurable.percent_complete
                valid_measurables += 1

        if valid_measurables == 0:
            return 0

        return total_percent / valid_measurables

    def calculate_okr_score(self):
        """Calculate OKR score (0.0-1.0) based on KR achievement"""
        if not self.measurables:
            return 0.0

        total_score = 0
        valid_krs = 0

        for kr in self.measurables:
            if (kr.committed_target and kr.baseline_value and
                kr.current_value is not None):

                # Calculate progress from baseline to committed target
                baseline_to_target = kr.committed_target - kr.baseline_value
                if baseline_to_target == 0:
                    score = 1.0 if kr.current_value >= kr.committed_target else 0.0
                else:
                    progress = (kr.current_value - kr.baseline_value) / baseline_to_target
                    score = min(max(progress, 0.0), 1.0)  # Clamp between 0.0 and 1.0

                total_score += score
                valid_krs += 1

        if valid_krs == 0:
            return 0.0

        return total_score / valid_krs

    def validate_measurables(self):
        """Validate measurable data"""
        for measurable in self.measurables:
            if measurable.baseline_value == measurable.committed_target:
                frappe.throw(f"Baseline value cannot be equal to committed target for KR: {measurable.metric_name}")

            if measurable.stretch_target and measurable.stretch_target <= measurable.committed_target:
                frappe.throw(f"Stretch target must be higher than committed target for KR: {measurable.metric_name}")

    def get_parent_info(self):
        """Get parent information (KR or OKR)"""
        if self.parent_kra:
            metric_name, _ = parse_parent_kra(self.parent_kra)
            if not metric_name:
                return None
            try:
                return {
                    "type": "KR",
                    "name": metric_name,
                    "doctype": "KR",
                    "doc": frappe.get_doc("KR", metric_name)
                }
            except frappe.DoesNotExistError:
                return None
        elif self.parent_okr:
            try:
                return {
                    "type": "OKR",
                    "name": self.parent_okr,
                    "doctype": "OKR",
                    "doc": frappe.get_doc("OKR", self.parent_okr)
                }
            except frappe.DoesNotExistError:
                return None
        return None

    def _get_status_category(self, okr):
        """Get status category for an OKR based on progress and target date"""
        progress = okr.get('progress', 0) or 0
        target_date = okr.get('target_date')

        if not target_date:
            if progress >= 100:
                return 'completed'
            elif progress >= 70:
                return 'on_track'
            else:
                return 'at_risk'

        from frappe.utils import getdate, nowdate
        days_remaining = (getdate(target_date) - getdate(nowdate())).days

        if progress >= 100:
            return 'completed'
        elif days_remaining < 0:
            return 'overdue'
        elif days_remaining <= 7:
            if progress < 80:
                return 'at_risk'
            else:
                return 'on_track'
        elif progress < 60:
            return 'at_risk'
        else:
            return 'on_track'

    def validate_okr_structure(self):
        """Validate OKR structure and hierarchy"""
        if self.okr_type == "Company" and self.parent_okr:
            frappe.throw("Company OKRs cannot have parent OKRs")

        if self.okr_type != "Company" and not self.parent_okr:
            frappe.msgprint("Consider linking this OKR to a Company OKR for better alignment")

    def update_measurable_targets(self):
        """Update measurable percent complete for all measurables"""
        for i, measurable in enumerate(self.measurables or []):
            if not self.name or not measurable.metric_name:
                continue
            stored_kra = _stored_parent_kra_for_measurable(self, measurable, i)
            child_okrs_with_kra = frappe.get_all(
                "OKR",
                filters={
                    "parent_okr": self.name,
                    "parent_kra": stored_kra
                },
                fields=["name"]
            )

            if child_okrs_with_kra:
                total_measurable_progress = 0
                valid_measurable_count = 0
                for child_okr in child_okrs_with_kra:
                    try:
                        child_doc = frappe.get_doc("OKR", child_okr.name)
                        if child_doc.measurables:
                            for child_measurable in child_doc.measurables:
                                if child_measurable.percent_complete is None:
                                    if child_measurable.current_value is not None and child_measurable.committed_target is not None and child_measurable.baseline_value is not None:
                                        baseline_to_target = child_measurable.committed_target - child_measurable.baseline_value
                                        if baseline_to_target != 0:
                                            progress = (child_measurable.current_value - child_measurable.baseline_value) / baseline_to_target
                                            child_measurable.percent_complete = min(max(progress * 100, 0), 100)
                                        else:
                                            child_measurable.percent_complete = 100 if child_measurable.current_value >= child_measurable.committed_target else 0
                                    else:
                                        child_measurable.percent_complete = 0
                                if child_measurable.percent_complete is not None:
                                    total_measurable_progress += child_measurable.percent_complete
                                    valid_measurable_count += 1
                    except Exception as e:
                        frappe.log_error(f"Error getting child OKR measurables for {child_okr.name}: {str(e)}")

                if valid_measurable_count > 0:
                    calculated_progress = round(total_measurable_progress / valid_measurable_count, 2)
                    measurable.percent_complete = calculated_progress
                    continue
                if measurable.percent_complete is None:
                    measurable.percent_complete = 0
                continue

            # No child OKRs linked (or OKR not saved yet), calculate from current_value as before
            if measurable.current_value is not None:
                if measurable.committed_target is not None and measurable.baseline_value is not None:
                    baseline_to_target = measurable.committed_target - measurable.baseline_value
                    if baseline_to_target != 0:
                        progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                        measurable.percent_complete = min(max(progress * 100, 0), 100)
                    else:
                        # If baseline equals target, check if current value meets or exceeds target
                        measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                else:
                    measurable.percent_complete = 0
            else:
                measurable.percent_complete = 0

    def set_next_check_in(self):
        """Set next check-in date based on frequency"""
        if not self.check_in_frequency:
            return

        if not self.last_check_in:
            self.last_check_in = nowdate()

        frequency_days = {
            "Weekly": 7,
            "Bi-weekly": 14,
            "Monthly": 30
        }

        days_to_add = frequency_days.get(self.check_in_frequency, 7)
        self.next_check_in = add_days(self.last_check_in, days_to_add)

    def update_parent_okr_progress(self):
        """Update parent progress if this is a child (OKR parent only, KR is read-only)"""
        # Only update if parent is OKR (KR is a standard doctype, we can't update it)
        if self.parent_okr:
            try:
                parent = frappe.get_doc("OKR", self.parent_okr)
                parent.progress = parent.calculate_progress()
                parent.okr_score = parent.calculate_okr_score()
                parent.save()
            except Exception as e:
                frappe.log_error(f"Error updating parent OKR progress: {str(e)}")

    def update_parent_measurable_progress(self):
        """Update parent OKR's measurable progress if this child OKR is linked via parent_kra"""
        if not self.parent_okr:
            return

        try:
            parent = frappe.get_doc("OKR", self.parent_okr)
            old_parent_kra = None

            # Check if parent_kra was changed
            if not self.is_new():
                doc_before_save = self.get_doc_before_save()
                if doc_before_save:
                    old_parent_kra = doc_before_save.get("parent_kra")

            # Update old parent_kra's measurable if it was changed/removed
            if old_parent_kra and old_parent_kra != self.parent_kra:
                self._update_measurable_for_kra(parent, old_parent_kra)

            # Update current parent_kra's measurable if it exists
            if self.parent_kra:
                self._update_measurable_for_kra(parent, self.parent_kra)

            # Recalculate all measurables to ensure they're up to date
            parent.update_measurable_targets()

            # Save parent to persist the measurable progress updates
            parent.save()
        except Exception as e:
            frappe.log_error(f"Error updating parent measurable progress: {str(e)}")

    def _update_measurable_for_kra(self, parent, kra_value):
        """Update parent measurable progress for this stored parent_kra (metric_name or metric_name||idx)."""
        metric_name, idx = parse_parent_kra(kra_value)
        if not metric_name:
            return
        for i, measurable in enumerate(parent.measurables or []):
            if measurable.metric_name != metric_name:
                continue
            if idx is not None and i != idx:
                continue
            stored_kra = _stored_parent_kra_for_measurable(parent, measurable, i)
            child_okrs_with_kra = frappe.get_all(
                "OKR",
                filters={
                    "parent_okr": self.parent_okr,
                    "parent_kra": stored_kra
                },
                fields=["name"]
            )

            if child_okrs_with_kra:
                total_measurable_progress = 0
                valid_measurable_count = 0
                for child_okr in child_okrs_with_kra:
                    try:
                        child_doc = frappe.get_doc("OKR", child_okr.name)
                        child_doc.update_measurable_targets()
                        if child_doc.measurables:
                            for child_measurable in child_doc.measurables:
                                if child_measurable.percent_complete is None:
                                    if child_measurable.current_value is not None and child_measurable.committed_target is not None and child_measurable.baseline_value is not None:
                                        baseline_to_target = child_measurable.committed_target - child_measurable.baseline_value
                                        if baseline_to_target != 0:
                                            progress = (child_measurable.current_value - child_measurable.baseline_value) / baseline_to_target
                                            child_measurable.percent_complete = min(max(progress * 100, 0), 100)
                                        else:
                                            child_measurable.percent_complete = 100 if child_measurable.current_value >= child_measurable.committed_target else 0
                                    else:
                                        child_measurable.percent_complete = 0
                                if child_measurable.percent_complete is not None:
                                    total_measurable_progress += child_measurable.percent_complete
                                    valid_measurable_count += 1
                    except Exception as e:
                        frappe.log_error(f"Error getting child OKR measurables for {child_okr.name}: {str(e)}")

                if valid_measurable_count > 0:
                    measurable.percent_complete = round(total_measurable_progress / valid_measurable_count, 2)
                else:
                    measurable.percent_complete = 0
            else:
                if measurable.current_value is not None and measurable.committed_target is not None and measurable.baseline_value is not None:
                    baseline_to_target = measurable.committed_target - measurable.baseline_value
                    if baseline_to_target != 0:
                        progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                        measurable.percent_complete = min(max(progress * 100, 0), 100)
                    else:
                        measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                else:
                    measurable.percent_complete = 0
            break

    def get_measurable_summary(self):
        """Get comprehensive summary of measurables with market-standard metrics"""
        if not self.measurables:
            return {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "not_started": 0,
                "at_risk": 0,
                "on_track": 0,
                "ahead_of_schedule": 0,
                "average_progress": 0,
                "average_confidence": 0,
                "leading_indicators": 0,
                "lagging_indicators": 0,
                "overdue_count": 0,
                "due_soon_count": 0,
                "progress_distribution": {
                    "excellent": 0,  # 90-100%
                    "good": 0,       # 70-89%
                    "fair": 0,       # 50-69%
                    "poor": 0,       # 30-49%
                    "critical": 0    # 0-29%
                },
                "confidence_distribution": {
                    "high": 0,       # 80-100%
                    "medium": 0,     # 60-79%
                    "low": 0         # 0-59%
                }
            }

        from frappe.utils import getdate, add_days, nowdate

        total = len(self.measurables)
        completed = 0
        in_progress = 0
        not_started = 0
        at_risk = 0
        on_track = 0
        ahead_of_schedule = 0
        total_progress = 0
        total_confidence = 0
        leading_indicators = 0
        lagging_indicators = 0
        overdue_count = 0
        due_soon_count = 0

        # Distribution counters
        progress_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "critical": 0}
        confidence_dist = {"high": 0, "medium": 0, "low": 0}

        today = getdate(nowdate())

        for measurable in self.measurables:
            # Basic status counting
            if measurable.percent_complete is None:
                not_started += 1
            elif measurable.percent_complete >= 100:
                completed += 1
            elif measurable.percent_complete > 0:
                in_progress += 1
            else:
                not_started += 1

            # Progress tracking
            if measurable.percent_complete is not None:
                total_progress += measurable.percent_complete

                # Progress distribution
                if measurable.percent_complete >= 90:
                    progress_dist["excellent"] += 1
                elif measurable.percent_complete >= 70:
                    progress_dist["good"] += 1
                elif measurable.percent_complete >= 50:
                    progress_dist["fair"] += 1
                elif measurable.percent_complete >= 30:
                    progress_dist["poor"] += 1
                else:
                    progress_dist["critical"] += 1

                # Risk assessment based on progress vs time
                if measurable.time_bound:
                    days_remaining = (getdate(measurable.time_bound) - today).days
                    progress_ratio = measurable.percent_complete / 100
                    if days_remaining < 0:  # Overdue
                        overdue_count += 1
                        at_risk += 1
                    elif days_remaining <= 7:  # Due soon
                        due_soon_count += 1
                        if progress_ratio < 0.8:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1
                    else:  # Normal timeline
                        if progress_ratio < 0.6:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1

            # Confidence tracking
            if measurable.confidence_level is not None:
                total_confidence += measurable.confidence_level

                # Confidence distribution
                if measurable.confidence_level >= 80:
                    confidence_dist["high"] += 1
                elif measurable.confidence_level >= 60:
                    confidence_dist["medium"] += 1
                else:
                    confidence_dist["low"] += 1

            # KR Type counting
            if measurable.kr_type == "Leading":
                leading_indicators += 1
            elif measurable.kr_type == "Lagging":
                lagging_indicators += 1

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "not_started": not_started,
            "at_risk": at_risk,
            "on_track": on_track,
            "ahead_of_schedule": ahead_of_schedule,
            "average_progress": round(total_progress / total, 1) if total > 0 else 0,
            "average_confidence": round(total_confidence / total, 1) if total > 0 else 0,
            "leading_indicators": leading_indicators,
            "lagging_indicators": lagging_indicators,
            "overdue_count": overdue_count,
            "due_soon_count": due_soon_count,
            "progress_distribution": progress_dist,
            "confidence_distribution": confidence_dist,
            "completion_rate": round((completed / total) * 100, 1) if total > 0 else 0,
            "risk_score": round((at_risk / total) * 100, 1) if total > 0 else 0,
            "overall_health": self._calculate_overall_health(progress_dist, confidence_dist, overdue_count, total)
        }

    def _calculate_overall_health(self, progress_dist, confidence_dist, overdue_count, total):
        """Calculate overall health score (0-100)"""
        if total == 0:
            # If no measurables, calculate health based on okr progress and confidence
            if hasattr(self, 'progress') and hasattr(self, 'confidence_level'):
                progress_score = self.progress or 0
                confidence_score = self.confidence_level or 50
                return round((progress_score + confidence_score) / 2, 1)
            return 0

        # Weight factors
        progress_weight = 0.4
        confidence_weight = 0.3
        timeline_weight = 0.3

        # Progress score (0-100)
        progress_score = (
            progress_dist["excellent"] * 100 +
            progress_dist["good"] * 80 +
            progress_dist["fair"] * 60 +
            progress_dist["poor"] * 40 +
            progress_dist["critical"] * 20
        ) / total

        # Confidence score (0-100) - handle case where no confidence data
        confidence_score = 0
        if sum(confidence_dist.values()) > 0:
            confidence_score = (
                confidence_dist["high"] * 100 +
                confidence_dist["medium"] * 70 +
                confidence_dist["low"] * 40
            ) / sum(confidence_dist.values())
        else:
            confidence_score = 50  # Default to neutral if no confidence data

        # Timeline score (0-100) - penalize overdue items
        timeline_score = max(0, 100 - (overdue_count / total) * 50)

        # Calculate weighted average
        overall_health = (
            progress_score * progress_weight +
            confidence_score * confidence_weight +
            timeline_score * timeline_weight
        )

        return round(overall_health, 1)



    def get_risk_summary(self):
        """Get summary of risks and blockers"""
        if not self.blockers:
            return {
                "total_blockers": 0,
                "critical_blockers": 0,
                "resolved_blockers": 0
            }

        total_blockers = len(self.blockers)
        critical_blockers = len([b for b in self.blockers if b.priority == "Critical"])
        resolved_blockers = len([b for b in self.blockers if b.status == "Resolved"])

        return {
            "total_blockers": total_blockers,
            "critical_blockers": critical_blockers,
            "resolved_blockers": resolved_blockers
        }

    def get_okr_grade(self):
        """Get OKR grade based on score"""
        score = self.okr_score or 0.0

        if score >= 0.7:
            return "A"
        elif score >= 0.4:
            return "B"
        elif score >= 0.1:
            return "C"
        else:
            return "D"

    @staticmethod
    @frappe.whitelist()
    def get_measurable_summary_static(okr_name):
        """Static method to get measurable summary for frontend"""
        doc = frappe.get_doc("OKR", okr_name)
        return doc.get_measurable_summary()

# Server-side functions for frontend calls
@frappe.whitelist()
def get_measurable_summary_for_frontend(okr_name):
    """Get measurable summary for frontend display"""
    doc = frappe.get_doc("OKR", okr_name)
    return doc.get_measurable_summary()

def parse_parent_kra(value):
    """
    Parse parent_kra stored value: "metric_name" or "metric_name||idx" for duplicate KRs.
    Returns (metric_name, idx or None).
    """
    if not value or not isinstance(value, str):
        return (None, None)
    parts = value.strip().split("||", 1)
    metric_name = parts[0].strip() if parts[0] else None
    idx = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None
    return (metric_name, idx)


def _stored_parent_kra_for_measurable(parent_doc, measurable, row_idx):
    """Value to store in parent_kra for this measurable row (unique when same KR has multiple titles)."""
    from collections import Counter
    names = [m.metric_name for m in (parent_doc.measurables or []) if m.metric_name]
    if Counter(names)[measurable.metric_name] > 1:
        return f"{measurable.metric_name}||{row_idx}"
    return measurable.metric_name


def _get_parent_kra_options_with_title(parent_okr):
    """
    Return all measurables from parent OKR. Each option: [value, description].
    When same KR appears multiple times (different titles), value = "metric_name||idx" so each is visible.
    """
    if not parent_okr:
        return []
    try:
        parent_doc = frappe.get_doc("OKR", parent_okr)
        from collections import Counter
        names = [m.metric_name for m in (parent_doc.measurables or []) if m.metric_name]
        counts = Counter(names)
        out = []
        for idx, measurable in enumerate(parent_doc.measurables or []):
            if not measurable.metric_name:
                continue
            metric_name = measurable.metric_name
            kr_title = (getattr(measurable, "kr_title", None) or "").strip()
            description = f"{metric_name} — {kr_title}" if kr_title else metric_name
            # Unique value when same KR has multiple titles so duplicates show as separate options
            value = f"{metric_name}||{idx}" if counts[metric_name] > 1 else metric_name
            out.append([value, description])
        return out
    except frappe.DoesNotExistError:
        return []
    except Exception as e:
        frappe.log_error(f"Error getting parent KRA options: {str(e)}")
        return []


@frappe.whitelist()
def get_krs_from_parent_okr(parent_okr):
    """Get list of unique KR names from parent OKR's measurables (for filters)."""
    options = _get_parent_kra_options_with_title(parent_okr)
    seen = set()
    out = []
    for opt in options:
        name, _ = parse_parent_kra(opt[0])
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


@frappe.whitelist()
def get_parent_kr_options(parent_okr):
    """Options for Parent KR: all measurables with title; value is unique (metric_name or metric_name||idx)."""
    options = _get_parent_kra_options_with_title(parent_okr)
    return [{"value": o[0], "label": o[1]} for o in options]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def parent_kra_link_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom Link query for Parent KR: all measurables from parent OKR, with title.
    Uses unique value (metric_name||idx) when same KR has different titles so duplicates are visible.
    """
    parent_okr = (filters or {}).get("parent_okr")
    options = _get_parent_kra_options_with_title(parent_okr)
    if not options:
        return []
    txt = (txt or "").strip().lower()
    if txt:
        options = [o for o in options if txt in (o[0] + " " + (o[1] or "")).lower()]
    return options[start : start + page_len]

@frappe.whitelist()
def get_child_kra_progress(okr_name):
    """Get child KRA progress data for each measurable in the parent OKR"""
    if not okr_name:
        return []

    try:
        parent_doc = frappe.get_doc("OKR", okr_name)
        result = []

        for i, measurable in enumerate(parent_doc.measurables or []):
            if not measurable.metric_name:
                continue
            stored_kra = _stored_parent_kra_for_measurable(parent_doc, measurable, i)
            child_okrs = frappe.get_all(
                "OKR",
                filters={
                    "parent_okr": okr_name,
                    "parent_kra": stored_kra
                },
                fields=["name", "title", "progress"]
            )

            if child_okrs:
                # Get all measurables from child OKRs
                child_measurables = []
                total_progress = 0
                valid_count = 0

                for child_okr in child_okrs:
                    try:
                        child_doc = frappe.get_doc("OKR", child_okr.name)
                        if child_doc.measurables:
                            for child_measurable in child_doc.measurables:
                                # Calculate percent_complete if not set
                                if child_measurable.percent_complete is None:
                                    if child_measurable.current_value is not None:
                                        if child_measurable.committed_target is not None and child_measurable.baseline_value is not None:
                                            baseline_to_target = child_measurable.committed_target - child_measurable.baseline_value
                                            if baseline_to_target != 0:
                                                progress = (child_measurable.current_value - child_measurable.baseline_value) / baseline_to_target
                                                child_measurable.percent_complete = min(max(progress * 100, 0), 100)
                                            else:
                                                child_measurable.percent_complete = 100 if child_measurable.current_value >= child_measurable.committed_target else 0
                                        else:
                                            child_measurable.percent_complete = 0
                                    else:
                                        child_measurable.percent_complete = 0

                                if child_measurable.percent_complete is not None:
                                    child_measurables.append({
                                        "okr_name": child_okr.name,
                                        "okr_title": child_okr.title,
                                        "kr_name": child_measurable.metric_name or "N/A",
                                        "kr_title": getattr(child_measurable, 'kr_title', None) or child_measurable.metric_name or "N/A",
                                        "progress": round(child_measurable.percent_complete, 2),
                                        "current_value": child_measurable.current_value,
                                        "baseline_value": child_measurable.baseline_value,
                                        "committed_target": child_measurable.committed_target
                                    })
                                    total_progress += child_measurable.percent_complete
                                    valid_count += 1
                    except Exception as e:
                        frappe.log_error(f"Error getting child OKR {child_okr.name} measurables: {str(e)}")

                if valid_count > 0:
                    avg_progress = round(total_progress / valid_count, 2)
                    result.append({
                        "parent_kr_name": measurable.metric_name,
                        "parent_kr_title": getattr(measurable, 'kr_title', None) or measurable.metric_name,
                        "stored_parent_kra": stored_kra,
                        "child_okr_count": len(child_okrs),
                        "child_measurable_count": len(child_measurables),
                        "average_progress": avg_progress,
                        "child_measurables": child_measurables
                    })

        return result
    except Exception as e:
        frappe.log_error(f"Error getting child KRA progress: {str(e)}")
        return []

@frappe.whitelist()
def get_child_okrs(okr_name):
    """Get child OKRs for an OKR (OKRs that have this OKR as their parent_okr)"""
    child_okrs = []

    if not okr_name:
        return child_okrs

    # Get OKRs that have this OKR as parent (parent_okr = this OKR's name)
    child_okrs = frappe.get_all(
        "OKR",
        filters={"parent_okr": okr_name},
        fields=["name", "title", "progress", "okr_score", "responsible_person",
               "target_date", "risk_status", "confidence_level", "okr_type"],
        order_by="creation desc"
    )

    # Add status category and format data
    for child in child_okrs:
        child['status_category'] = _get_status_category_for_okr(child)
        child['progress_display'] = f"{child.get('progress', 0):.1f}%"
        child['score_display'] = f"{child.get('okr_score', 0):.2f}"

    return child_okrs

def _get_status_category_for_okr(okr):
    """Get status category for an OKR based on progress and target date"""
    progress = okr.get('progress', 0) or 0
    target_date = okr.get('target_date')

    if not target_date:
        if progress >= 100:
            return 'completed'
        elif progress >= 70:
            return 'on_track'
        else:
            return 'at_risk'

    from frappe.utils import getdate, nowdate
    days_remaining = (getdate(target_date) - getdate(nowdate())).days

    if progress >= 100:
        return 'completed'
    elif days_remaining < 0:
        return 'overdue'
    elif days_remaining <= 7:
        if progress < 80:
            return 'at_risk'
        else:
            return 'on_track'
    elif progress < 60:
        return 'at_risk'
    else:
        return 'on_track'

@frappe.whitelist()
def get_okr_type_options():
    """Fetch okr_type options from OKR Setting's child table."""
    setting = frappe.get_single("OKR Setting")
    return [row.okr_type for row in setting.okr_types]
