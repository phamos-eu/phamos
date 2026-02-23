# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import nowdate, add_days, getdate
from frappe.model.document import Document

class OKR(Document):
    def validate(self):
        self.validate_measurables()
        self.validate_and_update_is_group()

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
                # Find the measurable in parent that matches this parent_kra
                for measurable in parent.measurables:
                    if measurable.metric_name == self.parent_kra:
                        # Recalculate progress for this measurable based on remaining child OKRs
                        child_okrs_with_kra = frappe.get_all(
                            "OKR",
                            filters={
                                "parent_okr": self.parent_okr,
                                "parent_kra": measurable.metric_name,
                                "name": ["!=", self.name]  # Exclude this OKR being deleted
                            },
                            fields=["name", "progress"]
                        )

                        if child_okrs_with_kra:
                            # Calculate average progress from remaining child OKRs' measurables
                            total_measurable_progress = 0
                            valid_measurable_count = 0

                            for child_okr in child_okrs_with_kra:
                                # Get the child OKR document to access its measurables
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
                            # No more child OKRs linked, reset to 0 or calculate from current_value
                            if measurable.current_value is not None:
                                if measurable.committed_target is not None and measurable.baseline_value is not None:
                                    baseline_to_target = measurable.committed_target - measurable.baseline_value
                                    if baseline_to_target != 0:
                                        progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                                        measurable.percent_complete = min(max(progress * 100, 0), 100)
                                    else:
                                        measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                                else:
                                    measurable.percent_complete = 0
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
            try:
                return {
                    "type": "KR",
                    "name": self.parent_kra,
                    "doctype": "KR",
                    "doc": frappe.get_doc("KR", self.parent_kra)
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

    def validate_and_update_is_group(self):
        """Validate and auto-manage is_group field based on children and parent relationships"""
        # Step 1: Update parent OKR's is_group when this OKR is selected as child
        if self.parent_okr:
            parent_is_group = frappe.db.get_value("OKR", self.parent_okr, "is_group")

            if parent_is_group is None:
                frappe.throw(f"Parent OKR '{self.parent_okr}' does not exist")

            # Automatically set is_group = 1 on parent if not already set
            if not parent_is_group:
                frappe.db.set_value("OKR", self.parent_okr, "is_group", 1, update_modified=False)
                frappe.db.commit()

        # Step 2: Update old parent's is_group if parent_okr was changed/removed
        if not self.is_new():
            doc_before_save = self.get_doc_before_save()
            if doc_before_save:
                old_parent_okr = doc_before_save.get("parent_okr") or ""
                current_parent_okr = self.get("parent_okr") or ""

                # If parent_okr was changed or removed (old had value, current is empty/None)
                if old_parent_okr and old_parent_okr != current_parent_okr:
                    # Count remaining children for old parent (excluding this record)
                    remaining_children = frappe.db.count(
                        "OKR",
                        filters={"parent_okr": old_parent_okr, "name": ["!=", self.name]}
                    )

                    # If old parent has no children left, uncheck is_group
                    if remaining_children == 0:
                        frappe.db.set_value("OKR", old_parent_okr, "is_group", 0, update_modified=False)
                        frappe.db.commit()

        # Step 3: Ensure this OKR's is_group is correct based on its children
        # Check if this OKR has any children (excluding self for new records)
        if self.is_new():
            child_count = 0  # New OKR can't have children yet
        else:
            child_count = frappe.db.count("OKR", filters={"parent_okr": self.name})

        # If OKR has children, ensure is_group = 1
        if child_count > 0:
            if not self.is_group:
                self.is_group = 1
        # If OKR has no children, is_group can be 0 (unchecked)
        # Since is_group is read-only, users can't manually change it


    def validate_okr_structure(self):
        """Validate OKR structure and hierarchy"""
        if self.okr_type == "Company" and self.parent_okr:
            frappe.throw("Company OKRs cannot have parent OKRs")

        if self.okr_type != "Company" and not self.parent_okr:
            frappe.msgprint("Consider linking this OKR to a Company OKR for better alignment")

    def update_measurable_targets(self):
        """Update measurable percent complete for all measurables"""
        for measurable in self.measurables:
            # Only check for child OKRs if this OKR is already saved (has a name)
            # and if the measurable has a metric_name (KR) set
            if self.name and measurable.metric_name:
                # Check if any child OKRs are linked to this measurable's KR via parent_kra
                child_okrs_with_kra = frappe.get_all(
                    "OKR",
                    filters={
                        "parent_okr": self.name,
                        "parent_kra": measurable.metric_name
                    },
                    fields=["name"]
                )

                # If child OKRs are linked to this KR, use their measurables' progress
                if child_okrs_with_kra:
                    # Get all measurables from all child OKRs linked to this KR
                    total_measurable_progress = 0
                    valid_measurable_count = 0
                    for child_okr in child_okrs_with_kra:
                        # Get the child OKR document to access its measurables
                        try:
                            child_doc = frappe.get_doc("OKR", child_okr.name)
                            # Ensure child OKR's measurables have percent_complete calculated
                            # This is important because measurables might not have percent_complete set
                            if child_doc.measurables:
                                for child_measurable in child_doc.measurables:
                                    # Calculate percent_complete if not already set
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

                                    # Add to total if percent_complete is set
                                    if child_measurable.percent_complete is not None:
                                        total_measurable_progress += child_measurable.percent_complete
                                        valid_measurable_count += 1
                        except Exception as e:
                            frappe.log_error(f"Error getting child OKR measurables for {child_okr.name}: {str(e)}")

                    if valid_measurable_count > 0:
                        # Use average progress from child OKRs' measurables
                        calculated_progress = round(total_measurable_progress / valid_measurable_count, 2)
                        measurable.percent_complete = calculated_progress
                        continue  # Skip the current_value calculation below
                    else:
                        # No valid measurables found in child OKRs, but child OKRs exist
                        # Set to 0 or keep existing value
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
                # If no current_value and no child OKRs, keep existing percent_complete or set to 0
                if measurable.percent_complete is None:
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

    def _update_measurable_for_kra(self, parent, kra_name):
        """Helper method to update parent measurable progress for a specific KR"""
        # Find the measurable in parent that matches this KR
        for measurable in parent.measurables:
            if measurable.metric_name == kra_name:
                # Recalculate progress for this measurable based on all child OKRs' measurables
                child_okrs_with_kra = frappe.get_all(
                    "OKR",
                    filters={
                        "parent_okr": self.parent_okr,
                        "parent_kra": measurable.metric_name
                    },
                    fields=["name"]
                )

                if child_okrs_with_kra:
                    # Get all measurables from all child OKRs linked to this KR
                    total_measurable_progress = 0
                    valid_measurable_count = 0

                for child_okr in child_okrs_with_kra:
                    # Get the child OKR document to access its measurables
                    try:
                        child_doc = frappe.get_doc("OKR", child_okr.name)
                        # Ensure child OKR's measurables have percent_complete calculated
                        child_doc.update_measurable_targets()

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
                                    total_measurable_progress += child_measurable.percent_complete
                                    valid_measurable_count += 1
                    except Exception as e:
                        frappe.log_error(f"Error getting child OKR measurables for {child_okr.name}: {str(e)}")

                    if valid_measurable_count > 0:
                        # Use average progress from child OKRs' measurables
                        measurable.percent_complete = round(total_measurable_progress / valid_measurable_count, 2)
                    else:
                        measurable.percent_complete = 0
                else:
                    # No child OKRs linked, calculate from current_value
                    if measurable.current_value is not None:
                        if measurable.committed_target is not None and measurable.baseline_value is not None:
                            baseline_to_target = measurable.committed_target - measurable.baseline_value
                            if baseline_to_target != 0:
                                progress = (measurable.current_value - measurable.baseline_value) / baseline_to_target
                                measurable.percent_complete = min(max(progress * 100, 0), 100)
                            else:
                                measurable.percent_complete = 100 if measurable.current_value >= measurable.committed_target else 0
                        else:
                            measurable.percent_complete = 0
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
                    "excellent": 0,
                    "good": 0,
                    "fair": 0,
                    "poor": 0,
                    "critical": 0
                },
                "confidence_distribution": {
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }
            }

        from frappe.utils import getdate, nowdate

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

        progress_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "critical": 0}
        confidence_dist = {"high": 0, "medium": 0, "low": 0}

        today = getdate(nowdate())

        for measurable in self.measurables:
            if measurable.percent_complete is None:
                not_started += 1
            elif measurable.percent_complete >= 100:
                completed += 1
            elif measurable.percent_complete > 0:
                in_progress += 1
            else:
                not_started += 1

            if measurable.percent_complete is not None:
                total_progress += measurable.percent_complete

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

                if hasattr(measurable, 'time_bound') and measurable.time_bound:
                    days_remaining = (getdate(measurable.time_bound) - today).days
                    progress_ratio = measurable.percent_complete / 100
                    if days_remaining < 0:
                        overdue_count += 1
                        at_risk += 1
                    elif days_remaining <= 7:
                        due_soon_count += 1
                        if progress_ratio < 0.8:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1
                    else:
                        if progress_ratio < 0.6:
                            at_risk += 1
                        elif progress_ratio >= 1.0:
                            ahead_of_schedule += 1
                        else:
                            on_track += 1

            if hasattr(measurable, 'confidence_level') and measurable.confidence_level is not None:
                total_confidence += measurable.confidence_level

                if measurable.confidence_level >= 80:
                    confidence_dist["high"] += 1
                elif measurable.confidence_level >= 60:
                    confidence_dist["medium"] += 1
                else:
                    confidence_dist["low"] += 1

            if hasattr(measurable, 'kr_type'):
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
            "overall_health": self._calculate_overall_health(progress_dist, confidence_dist, overdue_count, total) if hasattr(self, '_calculate_overall_health') else 0
        }

    def _calculate_overall_health(self, progress_dist, confidence_dist, overdue_count, total):
        """Calculate overall health score (0-100)"""
        if total == 0:
            if hasattr(self, 'progress') and hasattr(self, 'confidence_level'):
                progress_score = self.progress or 0
                confidence_score = self.confidence_level or 50
                return round((progress_score + confidence_score) / 2, 1)
            return 0

        progress_weight = 0.4
        confidence_weight = 0.3
        timeline_weight = 0.3

        progress_score = (
            progress_dist["excellent"] * 100 +
            progress_dist["good"] * 80 +
            progress_dist["fair"] * 60 +
            progress_dist["poor"] * 40 +
            progress_dist["critical"] * 20
        ) / total

        confidence_score = 0
        if sum(confidence_dist.values()) > 0:
            confidence_score = (
                confidence_dist["high"] * 100 +
                confidence_dist["medium"] * 70 +
                confidence_dist["low"] * 40
            ) / sum(confidence_dist.values())
        else:
            confidence_score = 50

        timeline_score = max(0, 100 - (overdue_count / total) * 50)

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
        critical_blockers = sum(1 for b in self.blockers if b.severity == "Critical")
        resolved_blockers = sum(1 for b in self.blockers if b.status == "Resolved")

        return {
            "total_blockers": total_blockers,
            "critical_blockers": critical_blockers,
            "resolved_blockers": resolved_blockers
        }

    def get_okr_grade(self):
        """Get OKR grade based on score"""
        score = self.okr_score or 0.0
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"

@frappe.whitelist()
def ensure_parent_is_group(parent_okr):
    """Ensure parent OKR has is_group = 1, update if needed"""
    if not parent_okr:
        return {"updated": False}

    parent_is_group = frappe.db.get_value("OKR", parent_okr, "is_group")

    if parent_is_group is None:
        frappe.throw(f"Parent OKR '{parent_okr}' does not exist")

    if not parent_is_group:
        frappe.db.set_value("OKR", parent_okr, "is_group", 1, update_modified=False)
        frappe.db.commit()
        return {"updated": True, "parent_okr": parent_okr}

    return {"updated": False}

# Standalone functions below (not part of OKR class)

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

@frappe.whitelist()
def get_krs_from_parent_okr(parent_okr):
    """Get list of KR names from parent OKR's measurables"""
    if not parent_okr:
        return []

    try:
        # Get the parent OKR document
        parent_doc = frappe.get_doc("OKR", parent_okr)

        # Extract unique KR names from measurables
        kr_names = []
        if parent_doc.measurables:
            for measurable in parent_doc.measurables:
                if measurable.metric_name and measurable.metric_name not in kr_names:
                    kr_names.append(measurable.metric_name)

        return kr_names
    except frappe.DoesNotExistError:
        return []
    except Exception as e:
        frappe.log_error(f"Error getting KRs from parent OKR: {str(e)}")
        return []

@frappe.whitelist()
def get_child_kra_progress(okr_name):
    """Get child KRA progress data for each measurable in the parent OKR"""
    if not okr_name:
        return []

    try:
        parent_doc = frappe.get_doc("OKR", okr_name)
        result = []

        # For each measurable in parent OKR
        for measurable in parent_doc.measurables:
            if not measurable.metric_name:
                continue

            # Find child OKRs linked to this KR via parent_kra
            child_okrs = frappe.get_all(
                "OKR",
                filters={
                    "parent_okr": okr_name,
                    "parent_kra": measurable.metric_name
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
def recalculate_measurable_progress(okr_name):
    """Recalculate measurable progress for an OKR (useful for refreshing on form load)"""
    try:
        if not okr_name:
            return False

        doc = frappe.get_doc("OKR", okr_name)
        doc.update_measurable_targets()
        doc.save()
        return True
    except Exception as e:
        frappe.log_error(f"Error recalculating measurable progress: {str(e)}")
        return False

@frappe.whitelist()
def get_okr_type_options():
    """Fetch okr_type options from OKR Setting's child table."""
    setting = frappe.get_single("OKR Setting")
    return [row.okr_type for row in setting.okr_types]
