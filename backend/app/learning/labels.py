"""Display names for salesperson feedback (§15)."""

from app.core.enums import FeedbackKind

FEEDBACK_LABELS = {
    FeedbackKind.GOOD_LEAD: "Good lead",
    FeedbackKind.BAD_LEAD: "Bad lead",
    FeedbackKind.CONTACTED: "Contacted",
    FeedbackKind.MEETING_BOOKED: "Meeting booked",
    FeedbackKind.PROPOSAL_SENT: "Proposal sent",
    FeedbackKind.WON: "Won",
    FeedbackKind.LOST: "Lost",
    FeedbackKind.WRONG_BUYER: "Wrong buyer",
    FeedbackKind.WRONG_SERVICE: "Wrong service",
    FeedbackKind.NOT_NOW: "Not now",
    FeedbackKind.NOT_ICP: "Not ICP",
    FeedbackKind.DUPLICATE: "Duplicate",
    FeedbackKind.COMPETITOR: "Competitor",
    FeedbackKind.OPPORTUNITY_CONFIRMED: "Opportunity confirmed",
    FeedbackKind.OPPORTUNITY_INCORRECT: "Opportunity incorrect",
}
