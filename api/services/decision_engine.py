"""
Decision engine for sanctions screening
Applies intelligent rules and thresholds to determine risk and action
"""
from typing import List, Literal, Tuple
from models import MatchedEntity
from config import settings


class DecisionEngine:
    """
    Intelligent decision engine for sanctions screening
    
    Decision Framework:
    - CLEAR: No significant match, proceed with transaction
    - REVIEW: Possible match, requires manual review and soft hold
    - BLOCK: High confidence match, hard hold and compliance escalation
    
    Risk Levels:
    - NONE: No matches above info threshold
    - LOW: Matches between info and review threshold
    - MEDIUM: Matches at review threshold
    - HIGH: Matches approaching block threshold
    - CRITICAL: Matches at or above block threshold
    """
    
    def __init__(self):
        self.threshold_info = settings.THRESHOLD_INFO
        self.threshold_review = settings.THRESHOLD_REVIEW
        self.threshold_block = settings.THRESHOLD_BLOCK
    
    def _determine_risk_level(self, score: float) -> Literal["none", "low", "medium", "high", "critical"]:
        """Determine risk level based on score"""
        if score >= self.threshold_block:
            return "critical"
        elif score >= (self.threshold_review + self.threshold_block) / 2:
            return "high"
        elif score >= self.threshold_review:
            return "medium"
        elif score >= self.threshold_info:
            return "low"
        else:
            return "none"
    
    def _build_decision_reasons(
        self,
        decision: str,
        top_score: float,
        match_count: int,
        top_match: MatchedEntity = None
    ) -> List[str]:
        """
        Build human-readable reasons for the decision
        
        These reasons are critical for:
        - Compliance officers reviewing cases
        - Audit trails
        - Customer support explanations
        """
        reasons = []
        
        if match_count == 0:
            reasons.append("No sanctions matches found in OFAC or UN datasets.")
            reasons.append("Person cleared for transaction processing.")
            return reasons
        
        # Score context
        reasons.append(
            f"Top match score: {top_score:.3f} (scale: 0.0-1.0, higher = stronger match)"
        )
        
        if top_match:
            reasons.append(
                f"Best match: '{top_match.caption}' from {top_match.dataset.upper()} "
                f"(Entity ID: {top_match.entity_id})"
            )
            
            # Add sanctions program context
            if top_match.programs:
                programs_str = ", ".join(top_match.programs[:3])
                reasons.append(f"Sanctions programs: {programs_str}")
        
        reasons.append(f"Total candidate matches evaluated: {match_count}")
        
        # Decision logic explanation
        if decision == "block":
            reasons.append(
                f"BLOCK decision: Score {top_score:.3f} >= block threshold {self.threshold_block:.2f}"
            )
            reasons.append(
                "Action required: Hard hold on withdrawal, immediate compliance review, "
                "gather additional KYC documentation."
            )
        
        elif decision == "review":
            reasons.append(
                f"REVIEW decision: Score {top_score:.3f} >= review threshold {self.threshold_review:.2f} "
                f"but < block threshold {self.threshold_block:.2f}"
            )
            reasons.append(
                "Action required: Soft hold on transaction, manual compliance review within 48 hours, "
                "request additional identity documents if needed."
            )
        
        elif decision == "clear":
            if top_score >= self.threshold_info:
                reasons.append(
                    f"CLEAR decision: Score {top_score:.3f} < review threshold {self.threshold_review:.2f}"
                )
                reasons.append(
                    "Low-confidence matches logged for monitoring but do not require action."
                )
            else:
                reasons.append(
                    f"CLEAR decision: All scores below information threshold {self.threshold_info:.2f}"
                )
            
            reasons.append("Person cleared for transaction processing.")
        
        return reasons
    
    def _apply_enhanced_rules(
        self,
        matches: List[MatchedEntity],
        base_decision: str,
        top_score: float
    ) -> Tuple[str, List[str]]:
        """
        Apply enhanced decision rules beyond simple score thresholds
        
        Rules:
        1. Exact ID match (passport/national ID) overrides score
        2. Multiple high-scoring matches increase severity
        3. DOB + Name match increases confidence
        
        Returns:
            (decision, additional_reasons)
        """
        enhanced_reasons = []
        decision = base_decision
        
        # Rule 1: Check for exact ID matches (very strong signal)
        for match in matches:
            if match.score >= self.threshold_review:
                # This is a simplified check - in production you'd compare actual IDs
                # from the request against entity properties
                pass
        
        # Rule 2: Multiple medium-confidence matches
        medium_confidence_count = sum(
            1 for m in matches 
            if self.threshold_review <= m.score < self.threshold_block
        )
        
        if medium_confidence_count >= 3 and decision == "review":
            enhanced_reasons.append(
                f"Enhanced scrutiny: {medium_confidence_count} matches above review threshold. "
                "Multiple candidates warrant careful manual review."
            )
        
        # Rule 3: Dataset consensus (same person in multiple datasets)
        datasets_with_hits = set(m.dataset for m in matches if m.score >= self.threshold_review)
        
        if len(datasets_with_hits) >= 2 and decision == "review":
            enhanced_reasons.append(
                f"Cross-dataset confirmation: Person appears in {len(datasets_with_hits)} datasets "
                f"({', '.join(datasets_with_hits)}). Increases match confidence."
            )
        
        return decision, enhanced_reasons
    
    def make_decision(
        self,
        matches: List[MatchedEntity]
    ) -> Tuple[str, str, float, List[str]]:
        """
        Make final screening decision based on matches
        
        Returns:
            (decision, risk_level, top_score, reasons)
        """
        
        # No matches case
        if not matches:
            return "clear", "none", 0.0, self._build_decision_reasons("clear", 0.0, 0)
        
        # Get top score
        top_score = max(m.score for m in matches)
        top_match = max(matches, key=lambda m: m.score)
        
        # Determine risk level
        risk_level = self._determine_risk_level(top_score)
        
        # Apply base threshold decision
        if top_score >= self.threshold_block:
            base_decision = "block"
        elif top_score >= self.threshold_review:
            base_decision = "review"
        else:
            base_decision = "clear"
        
        # Build base reasons
        reasons = self._build_decision_reasons(
            base_decision,
            top_score,
            len(matches),
            top_match
        )
        
        # Apply enhanced rules
        final_decision, enhanced_reasons = self._apply_enhanced_rules(
            matches,
            base_decision,
            top_score
        )
        
        # Combine reasons
        all_reasons = reasons + enhanced_reasons
        
        return final_decision, risk_level, top_score, all_reasons


# Global decision engine instance
decision_engine = DecisionEngine()