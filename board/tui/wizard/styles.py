from ..theme import AQUA, BLUE, CHIP, FIELD, INK, LINE, MUTED, PANEL, RAISED, RED

WIZARD_CSS = f"""
WizardScreen {{ align: center middle; }}
#wizard {{ width: 84; height: auto; max-height: 96%; background: {PANEL}; border: round {LINE}; padding: 0; }}
#wizard-head {{ height: auto; padding: 1 2 0 2; }}
#crumbs {{ height: 1; margin: 0 0 1 0; }}
#wizard-title {{ text-style: bold; color: {INK}; }}
#wizard-help {{ color: {MUTED}; margin: 0 0 1 0; }}
#wizard Rule {{ color: {LINE}; margin: 0; }}
#wizard-body {{ height: auto; padding: 1 2; }}
#wizard-foot {{ height: 3; padding: 0 2; }}
#wizard-foot .spacer {{ width: 1fr; }}
.btn {{ width: auto; height: 3; padding: 0 2; margin: 0 0 0 1; border: round {LINE}; background: {PANEL}; color: {INK}; content-align: center middle; }}
.btn:hover {{ border: round {MUTED}; }}
.btn.primary {{ background: {INK}; color: {FIELD}; border: round {INK}; text-style: bold; }}
.btn.danger {{ background: {RED}; color: #ffffff; border: round {RED}; text-style: bold; }}
.btn.ghost {{ border: round {PANEL}; color: {MUTED}; }}
.btn.ghost:hover {{ color: {INK}; }}
.btn.link {{ height: 1; border: none; margin: 0; padding: 0 1; }}
.btn:disabled {{ opacity: 40%; }}

.callout {{ height: auto; padding: 0 1; margin: 1 0 0 0; border-left: tall {BLUE}; background: {BLUE} 10%; color: {INK}; }}
.callout.error {{ border-left: tall {RED}; background: {RED} 10%; }}
.callout.warn {{ border-left: tall {AQUA}; background: {AQUA} 10%; }}
.box {{ height: auto; padding: 0 1; background: {CHIP}; margin: 1 0 0 0; }}
.code {{ height: auto; padding: 0 1; background: {FIELD}; color: {INK}; margin: 1 0 0 0; }}
.label {{ color: {INK}; text-style: bold; }}
.hint {{ color: {MUTED}; }}
.section {{ color: {MUTED}; text-style: bold; margin: 1 0 0 0; }}

SummaryView, ProgressView, ReadyView, MultiField {{ height: auto; }}
ChoiceInput {{ height: auto; }}
ChoiceInput.two {{ layout: grid; grid-size: 2; grid-gutter: 0 1; }}
ChoiceCard {{ height: auto; padding: 0 1; border: round {LINE}; }}
ChoiceInput.two ChoiceCard {{ height: 100%; }}
ChoiceCard.selected {{ border: round {INK}; background: {RAISED}; }}
TextField {{ height: auto; }}
TextField Input {{ border: round {LINE}; background: {FIELD}; padding: 0 1; }}
TextField Input:focus {{ border: round {INK}; }}
CheckList {{ height: auto; border: round {LINE}; }}
CheckRow {{ height: 2; padding: 0 1; }}
CheckRow.cursor {{ background: {RAISED}; }}
CheckList:focus {{ border: round {INK}; }}

RecapRow {{ height: 1; }}
RecapRow .key {{ width: 16; color: {MUTED}; }}
RecapRow .value {{ width: 1fr; }}
#recap {{ height: auto; padding: 0 1; border: round {LINE}; }}
#checks {{ height: auto; }}
#typed {{ border: round {LINE}; background: {FIELD}; margin: 1 0 0 0; }}
#log {{ height: 8; }}
"""
