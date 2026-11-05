from .theme import ALERT, AQUA, BLUE, GRAY, INK, MUTED, RUNNING, SEEN_RED, WAITING

APP_CSS = f"""
Screen {{ background: #0d1117; }}
#top {{ height: 3; padding: 1 2 0 2; }}
#main {{ height: 1fr; }}
#list {{ width: 1fr; padding: 0 1 0 2; scrollbar-size-vertical: 1; }}
#side {{ width: 1fr; min-width: 40; background: #161b22; border-left: tall #21262d; }}
#main.narrow {{ layout: vertical; }}
#main.narrow #list {{ width: 1fr; height: 2fr; }}
#main.narrow #side {{ width: 1fr; min-width: 0; height: 3fr; border-left: none; border-top: tall #21262d; }}
#preview {{ padding: 1 2; }}
#terminal-header {{ height: 2; padding: 0 2; margin: 1 0 0 0; }}
#terminal-view {{ height: 1fr; margin: 1 1 0 2; }}
#preview-head {{ height: auto; }}
#preview-actions {{ height: auto; margin: 1 0 0 0; }}
#preview-plain {{ height: auto; margin: 1 0 0 0; padding: 0 1; border-left: tall {AQUA} 50%; }}
#preview-sessions {{ height: auto; margin: 1 0 0 0; }}
#preview-sessions .section {{ margin: 0 0 0 0; }}
.session-row {{ height: 1; padding: 0 1; }}
.session-row:hover {{ background: {INK} 8%; }}
.session-row.picked {{ background: {INK} 10%; }}
#preview-body {{ height: auto; margin: 1 0 0 0; }}
SectionHeader {{ margin: 1 0 0 0; height: 2; padding: 0 1; }}
ItemGrid {{ grid-gutter: 1 2; height: auto; margin: 0 0 0 0; }}
.tile {{ text-wrap: nowrap; height: 6; min-height: 6; padding: 0 1; }}
.tile.your_move {{ background: {SEEN_RED} 12%; border: tall {SEEN_RED} 50%; }}
.tile.your_move:focus {{ background: {SEEN_RED} 24%; border: tall {SEEN_RED}; }}
.tile.alert {{ background: {ALERT} 12%; border: tall {ALERT} 50%; }}
.tile.alert:focus {{ background: {ALERT} 24%; border: tall {ALERT}; }}
#list.flash .tile.alert {{ background: {ALERT} 35%; border: tall {ALERT}; }}
.tile.working {{ background: {RUNNING} 10%; border: tall {RUNNING} 35%; }}
.tile.working:focus {{ background: {RUNNING} 22%; border: tall {RUNNING}; }}
.tile.setting_up {{ background: {BLUE} 10%; border: tall {BLUE} 35%; }}
.tile.setting_up:focus {{ background: {BLUE} 22%; border: tall {BLUE}; }}
.tile.reviewing {{ background: {BLUE} 10%; border: tall {BLUE} 35%; }}
.tile.reviewing:focus {{ background: {BLUE} 22%; border: tall {BLUE}; }}
.tile.in_review {{ background: {WAITING} 10%; border: tall {WAITING} 35%; }}
.tile.in_review:focus {{ background: {WAITING} 22%; border: tall {WAITING}; }}
.tile.done {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
.tile.done:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
.tile.ended {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
.tile.ended:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
RepoImage {{ position: absolute; }}
#empty {{ color: {MUTED}; padding: 1 1; }}
Footer {{ background: #0d1117; }}
"""
