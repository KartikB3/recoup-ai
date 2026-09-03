"""The fixed policy-rule order documented in ``docs/POLICY-SOURCES.md``."""

from recoup.policy.context import Rule
from recoup.policy.rules.batch_cluster_suppression import RULE as BATCH_CLUSTER_SUPPRESSION
from recoup.policy.rules.high_value_escalation import RULE as HIGH_VALUE_ESCALATION
from recoup.policy.rules.invoice_link_cap import RULE as INVOICE_LINK_CAP
from recoup.policy.rules.link_budget import RULE as LINK_BUDGET
from recoup.policy.rules.nothing_outstanding import RULE as NOTHING_OUTSTANDING
from recoup.policy.rules.payer_contact_frequency import RULE as PAYER_CONTACT_FREQUENCY
from recoup.policy.rules.payer_contact_spacing import RULE as PAYER_CONTACT_SPACING
from recoup.policy.rules.rbi_contact_hours import RULE as RBI_CONTACT_HOURS
from recoup.policy.rules.trai_message_category import RULE as TRAI_MESSAGE_CATEGORY
from recoup.policy.rules.trai_promotional_window import RULE as TRAI_PROMOTIONAL_WINDOW
from recoup.policy.rules.visible_dispute import RULE as VISIBLE_DISPUTE

RULE_ORDER: tuple[Rule, ...] = (
    NOTHING_OUTSTANDING,
    VISIBLE_DISPUTE,
    # After visible-dispute on purpose: an invoice with its own dispute is
    # routed on its own merits rather than absorbed into a group decision.
    BATCH_CLUSTER_SUPPRESSION,
    RBI_CONTACT_HOURS,
    TRAI_PROMOTIONAL_WINDOW,
    TRAI_MESSAGE_CATEGORY,
    PAYER_CONTACT_FREQUENCY,
    PAYER_CONTACT_SPACING,
    INVOICE_LINK_CAP,
    LINK_BUDGET,
    HIGH_VALUE_ESCALATION,
)

__all__ = ["RULE_ORDER"]
