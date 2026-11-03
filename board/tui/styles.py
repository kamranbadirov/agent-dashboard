from .theme import AQUA, BLUE, GRAY, GREEN, INK, MUTED, RED

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
.tile.your_move {{ background: {AQUA} 10%; border: tall {AQUA} 35%; }}
.tile.your_move:focus {{ background: {AQUA} 22%; border: tall {AQUA}; }}
.tile.working {{ background: {RED} 10%; border: tall {RED} 35%; }}
.tile.working:focus {{ background: {RED} 22%; border: tall {RED}; }}
.tile.setting_up {{ background: {BLUE} 10%; border: tall {BLUE} 35%; }}
.tile.setting_up:focus {{ background: {BLUE} 22%; border: tall {BLUE}; }}
.tile.reviewing {{ background: {BLUE} 10%; border: tall {BLUE} 35%; }}
.tile.reviewing:focus {{ background: {BLUE} 22%; border: tall {BLUE}; }}
.tile.in_review {{ background: {GREEN} 10%; border: tall {GREEN} 35%; }}
.tile.in_review:focus {{ background: {GREEN} 22%; border: tall {GREEN}; }}
.tile.done {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
.tile.done:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
.tile.ended {{ background: {GRAY} 10%; border: tall {GRAY} 35%; }}
.tile.ended:focus {{ background: {GRAY} 22%; border: tall {GRAY}; }}
RepoImage {{ position: absolute; }}
#empty {{ color: {MUTED}; padding: 1 1; }}
Footer {{ background: #0d1117; }}
"""
