"""English help shared by in-app topic windows and the offline guide."""
from pathlib import Path
from html import escape
import json

from pip_help_vi import DATA
VI_DATA=dict(DATA)
VI_UI=VI_DATA.pop('_ui')
VI_DATA={'quick':VI_DATA['quick'], **VI_DATA}
EN_UI={'title':'PIP User Guide','hint':'Choose a topic. Help does not change your EP or settings.',
       'search':'Search topics','close':'Close','subtitle':'English · Daily scheduling, media preparation and QC'}

TOPICS = {
 'quick': ('Start here — 3 basic steps', [
  ('1. Copy the starting-show notice', 'Open step 0: Enter information. Copy and paste the full “Next day will air…” notice for the EP you are preparing.'),
  ('2. Copy the start-of-day timing line', 'Paste the full timing line below the notice, including the End time and any ADD/MINUS information. Keep the original line; do not manually convert it.'),
  ('3. Click Run all', 'Click Run all. If PIP asks for a missing file or confirmation, resolve it and continue. When finished, read QC.')]),
 'timing_feedback': ('Adjust timing from playback feedback', [
  ('Paste WV and End', 'After building the schedule, click Adjust timing beside Build schedule. Paste both WV and End lines from the playback check of that exact M3U. MINUS shortens; ADD extends. Click Adjust and export schedule.'),
  ('Review the result', 'PIP refits the schedule using existing scheduling rules, exports M3U/QC, and reports remaining seconds. It may not find an exact fit. Check the new M3U on the playback computer. Identical pasted text is not applied twice. Settings are saved per EP; Reset to original targets removes the correction.')]),
 'start': ('Quick start & installation', [
  ('First use', 'Extract the complete ZIP to a writable folder. Run SCHEDULER.cmd. Keep the included runtime, INPUT.xlsx, ADS temps and sample files together. The package contains lightweight scheduling media, not the full broadcast videos.'),
  ('Before working', 'Make sure the source export folder is accessible on this computer. The default is W:\\@ SHOW EXPORTS. Check that INPUT.xlsx contains the correct day and ADS list. Save and close Excel after editing.'),
  ('Daily steps', '1. Select the EP.\n2. Enter or load the starting-show notice and any missing durations.\n3. Check FN, TSER FN, start block, start offset and MT shift.\n4. Click Run all and resolve the first file-check dialog.\n5. Review Cycle 1, All cycles and QC.\n6. Use Prepare files when you need the renamed original videos in the source EP temp folder.'),
  ('Two separate operations', 'Run all builds the local scheduling EP, playlist and QC. Prepare files copies original media into the source EP temp folder. Use each operation for its purpose; Run all does not replace Prepare.')]),
 'prepare': ('Prepare files / Update / Stop', [
  ('Prepare files', 'Copies selected original videos into the source EP folder under temp, using the approved local names. Existing destination files are kept. This folder can be large because these are original video copies, not lightweight placeholders.'),
  ('Update beside Prepare', 'Uses preparation history to copy new or changed sources. Unchanged sources already recorded as processed are skipped. If you deleted a prepared file and need it again, use Prepare files.'),
  ('Stop preparation', 'Stops the current copy operation and removes an unfinished partial copy. Completed copies remain available. Read the completion report for skipped files and their reasons.'),
  ('FN re-air', 'Selected FN parts from the previous EP are also copied to the current EP temp folder. Their local names use the current EP number, while event details, part numbers and REAIR remain. Original sources are not renamed.')]),
 'run': ('Run all / Scan EP / Create EP / Build schedule', [
  ('Last result', 'PIP saves the last completed schedule result per EP, including drafts. Reopening restores the most recently saved EP, cycle tables and QC without rebuilding. Switching EP loads its saved result. Use Run all for a fresh result. Older runs made before this feature need one new build to create a snapshot.'),
  ('Run all', 'Runs Scan EP → Create EP → Build schedule → QC. Resolve missing or uncertain files before continuing. A completed run can still contain QC errors; read the report.'),
  ('Scan EP', 'Reads INPUT and available source files for the chosen EP. Shows source names, proposed local names and available parts. Scan again after source files or INPUT change.'),
  ('Create EP', 'Builds lightweight local media for scheduling, using real-file durations when available and reported durations for missing media. These temps are not broadcast footage. A changed or incomplete source may stop this step.'),
  ('Build schedule', 'Uses the current local EP and settings to arrange cycles, fit MT/end-of-day timing, and write the playlist and QC. After changing source selection or names, scan and create the EP before rebuilding the schedule.')]),
 'settings': ('EP / FN / TSER FN / start & MT settings', [
  ('EP and Today', 'EP identifies the day being prepared. Today selects the date-based EP. Enter information for that EP; a starting notice with a different EP should be corrected. Saved information is loaded per EP.'),
  ('FN and TSER FN', 'FN enables the FN content set. TSER FN enables its teaser. The teaser prefers the gap after NWN S2 and before S3, twice in a full cycle. Timing adjustment may retain only one copy. FN re-air local files use the current EP number.'),
  ('Start block and Detect', 'Paste the starting-show notice and use Detect to match it against INPUT. Check both the EP number and the program order. Start block is the selected entry point in the cycle rotation.'),
  ('Start offset (seconds)', 'Sets the initial timing offset. Negative values start earlier; positive values start later. Verify the resulting times in QC.'),
  ('MT shift (shows)', 'Moves the selected MT placement earlier or later by show positions. Positive moves later; negative moves earlier. It changes placement, not a fixed number of minutes. The timing fitter still needs to meet the MT target; verify the actual time and position in QC.')]),
 'input': ('Starting notice / durations / INPUT', [
  ('Step 0', 'Paste the starting-show notice and any reported durations. Read and save information applies the text to the selected EP. Blank input should not erase information previously saved for another EP.'),
  ('Duration format', 'Use minutes:seconds, for example 00:40 for a 40-second teaser or 08:14 for a program part. Include the program/part label, such as AP PARTD. Real available media takes priority over a reported duration.'),
  ('Input workbook', 'Open INPUT to edit the program and daily ADS lists. Open the ADS table to inspect the catalog. Save spreadsheet changes, then Scan EP again.'),
  ('Missing or wrong names', 'The first check shows missing files and recognized files carrying the wrong EP. Accept for this EP explicitly approves the proposed local correction. The source filename stays unchanged. A replaced or changed source requires confirmation again.')]),
 'files': ('Files / Skip / Browse / accept a file', [
  ('ADS group', 'Click ADS group beside Browse, add two or more files, and use the up/down arrows to set playback order. Save group. The scheduler uses one slot and the combined duration; M3U lists the files consecutively. Skip applies to the whole group. Reopen ADS group to change it; Browse replaces it with one file. M3U QC flags incomplete or reordered groups.'),
  ('Files / Skip', 'Reopens the current EP selections, including found files and skipped items. Use this when you want to change a previous choice.'),
  ('Browse', 'Choose a replacement for the displayed item. For an FN set, select P1A to load the matching complete set. Read the confirmation list to avoid mixing events or parts.'),
  ('Skip today', 'Saves the skip for this EP. The item is not used, and Run all does not keep prompting for it. Open Files / Skip to undo it.'),
  ('Skip 1 time', 'Skips the item for one Run all in the current PIP session. It is cleared after the run. It does not permanently change that EP.'),
  ('Undo skip and acceptance', 'Undo skip restores the requirement. A successful Browse also clears that item’s skip. For a recognized wrong-EP file, tick Accept for this EP to use the corrected local name; untick it to revoke the choice.'),
  ('Recheck', 'After choosing files, recheck and continue so the EP and schedule are rebuilt. Other unresolved issues still appear even if some items have been skipped.')]),
 'content': ('EP content / durations / Lock / add a file', [
  ('Unlock before editing', 'Original rows are locked by default. Select a row, unlock it, then edit or double-click it. Lock protects the row from edits; it does not lock its playback position.'),
  ('File or reported duration', 'Choose a source file when it exists. If media is missing, enter its duration to create a scheduling temp. You can add another part, such as AP PARTD, without assuming a fixed part count.'),
  ('Content type and placement', 'Choose Show, Teaser, Priority ADS or Regular ADS as appropriate. For custom placement, specify the block, anchor item, before/after position and applicable cycles. Review the resulting order in Cycle 1 and All cycles.'),
  ('Restore and save', 'Restore defaults returns an original item to its detected settings. Remove is for added custom rows; use Files / Skip for ADS or teaser skips. Save applies changes to this EP; Cancel leaves the saved content unchanged.')]),
 'names': ('Source names / local names / Max', [
  ('Local name column', 'Double-click the local-name cell to edit it, then save the edited names. Keep the EP, program code, part/segment and required variant markers recognizable. Source files retain their names.'),
  ('Automatic shortening', 'Person-name titles follow the existing person rule. Other show titles use up to the first five words plus part and segment. Scan and rebuild the EP and schedule after changing the naming rule.'),
  ('Max and No Max', 'Keep these variants distinct. The Max checkbox applies to supported draft/reported-duration rows. Confirm which variant the duration describes before selecting it; the scheduler uses eligible variants to fit timing.'),
  ('AP versions', 'For each AP part, the latest version is selected; modification time resolves equal versions. Max and No Max are selected separately. The schedule chooses the appropriate variant rather than playing both consecutively.')]),
 'cycles': ('Cycle 1 / All cycles / M3U', [
  ('Cycle 1', 'Review the starting program, show order, segments and insertions before comparing the remaining cycles.'),
  ('All cycles', 'Inspect the full-day order and the timing columns. Show rows stay white; teaser, fixed ADS, daily ADS, added ADS and special items have distinct highlights. Warnings use yellow. Read labels and QC as well as colors.'),
  ('Segment insertions', 'Valid teasers may exceed two minutes in a segment gap. Regular ADS in that gap remain under two minutes. A gap should contain one insertion.'),
  ('Playlist', 'The generated M3U is written under the local _playlist folder; the report shows its exact path. Inspect QC before handing off. Local scheduling temps are not original broadcast videos; Prepare creates the original-video copies separately.')]),
 'qc': ('QC of the schedule you just built', [
  ('Timing', 'Check the actual MT time and placement, then the end-of-day time and final show. The usual tolerance is ±15 seconds. An allowed end-of-day exception is still shown explicitly.'),
  ('Daily ADS — section 3', 'DO NOT SKIP appears first, PRIORITY next, then regular ADS. Each cycle has a green check when present and a red cross when absent. Regular ADS used in at least three cycles are green; those below three are red. Presence colors describe usage; review timing exceptions and remaining errors too.'),
  ('Items to resolve — section 4', 'Read the specific file or rule error. Add/select the correct media, fix INPUT or adjust the relevant setting, then rebuild. Missing-ADS messages already represented in the daily ADS list are not repeated there.'),
  ('Adjustments and outputs', 'The report records Max changes, insertions and removals used for timing, followed by output paths. Review Cycle 1 and All cycles together with this report.')]),
 'external': ('Check external schedule: M3U or Word', [
  ('Choose the guide for your file', 'vMix check: use the M3U playlist. EP list check: use the Word DOCX list. Both start from Check external schedule. Select the matching topic in the guide for the short steps.'),
  ('Open and select', 'Use Check external schedule, then choose an M3U or Word DOCX made by someone else. Check the detected EP. Load or enter the starting-show notice from step 0.'),
  ('Start Check', 'Runs rule checks and compares the schedule with INPUT. If the starting notice is missing or unclear, correct it; choosing to skip that confirmation allows QC results to be shown but does not prove the starting order is correct.'),
  ('What is checked', 'Review the starting show, fixed rules, daily ADS by cycle, unusual show/teaser/FN content, and differences from Cycle 1. Word can list S1A/S1B/S1C together. Names are compared using EP, code, partial title and stated parts.'),
  ('Scope and report', 'This check does not evaluate MT/24-hour targets or measure durations by default. Read the report inside PIP. Save report exports the results; use the return-to-top button to navigate back to the beginning.')]),
 'check_m3u': ('vMix check — M3U', [
  ('1. Select the playlist', 'Click Check external schedule → Select M3U / Word. Choose the M3U playlist to be checked and confirm the detected EP.'),
  ('2. Starting show', 'Load the starting-show notice from step 0, or paste it if it is missing. Check that it belongs to this EP.'),
  ('3. Start Check', 'Click Start Check. Read the in-app QC: starting show, fixed rules, daily ADS, show/teaser/FN content and differences between cycles. This checks the playlist file, not the live vMix application. MT/24-hour timing and duration measurement are not checked by default.')]),
 'check_docx': ('EP list check — Word', [
  ('1. Select the EP list', 'Click Check external schedule → Select M3U / Word. Choose the Word DOCX EP list and confirm the EP.'),
  ('2. Starting show', 'Load the starting-show notice from step 0, or paste it if it is missing.'),
  ('3. Start Check', 'Click Start Check and read QC inside PIP. Checks compare the written list with INPUT and rules. NWN S1A/S1B/S1C may be combined in one entry. Later cycles follow Cycle 1 plus the changes stated in Word; unclear changes need confirmation. MT/24-hour timing and duration measurement are not checked by default.')]),
 'update': ('Update PIP / language / sharing', [
  ('Update ADS temps', 'Use Update ADS temps in the sidebar. It reads INPUT_4 from the current INPUT or a workbook you select. Click Update ADS temps to create missing lightweight files in @ ADS 2. Existing media is kept. Missing durations or ambiguous names are listed for review. If all listed ADS already exist and no review is needed, it reports: Nothing new in the list.'),
  ('Update PIP', 'Updates the program from the published Hub feed. Finish the current operation before updating and follow the updater prompts. This is different from Update beside Prepare, which updates copied media.'),
  ('Language', 'The sidebar language selector remembers the choice for the next launch. Help defaults to that choice. Switch Vietnamese / English inside the help window at any time without changing the application language.'),
  ('Sharing the package', 'Send the complete portable ZIP to a new user. It includes the program runtime, INPUT and lightweight ADS/sample media. Each computer still needs access to the original source exports. Existing users can use Update PIP for published program/INPUT changes; that feed does not distribute the full ADS media library.'),
  ('Help and processing order', 'Click an i button beside a control group for its guide. User guide opens all topics. PIP processing order describes the current scheduling rules and priorities.')]),
}

def show_help(parent, topic='quick', language=None):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    if language is None:
        from ui_language import get_language
        language=get_language()
    window=tk.Toplevel(parent);window.geometry('900x650')
    window.minsize(640,420);window.transient(parent)
    previous=parent.grab_current()
    if previous:window.grab_set()
    def close():
        window.destroy()
        if previous and previous.winfo_exists():previous.grab_set()
    window.protocol('WM_DELETE_WINDOW',close);window.bind('<Escape>',lambda e:close())
    outer=ttk.Frame(window,padding=14);outer.pack(fill='both',expand=True)
    header=ttk.Frame(outer);header.pack(fill='x')
    title_label=ttk.Label(header,font=('Segoe UI',17,'bold'));title_label.pack(side='left')
    lang=tk.StringVar(value='Tiếng Việt' if language=='vi' else 'English')
    selector=ttk.Combobox(header,textvariable=lang,values=('Tiếng Việt','English'),state='readonly',width=14)
    selector.pack(side='right')
    hint=ttk.Label(outer);hint.pack(anchor='w',pady=(2,12))
    pane=ttk.Panedwindow(outer,orient='horizontal');pane.pack(fill='both',expand=True)
    nav=ttk.Frame(pane);pane.add(nav,weight=1)
    search_label=ttk.Label(nav);search_label.pack(anchor='w')
    query=tk.StringVar();search=ttk.Entry(nav,textvariable=query);search.pack(fill='x',pady=(0,8))
    topics=tk.Listbox(nav,width=29,exportselection=False);topics.pack(fill='both',expand=True)
    body=ScrolledText(pane,wrap='word',font=('Segoe UI',11),padx=16,pady=12);pane.add(body,weight=3)
    body.tag_configure('title',font=('Segoe UI',16,'bold'),foreground='#183C59',spacing3=16)
    body.tag_configure('heading',font=('Segoe UI',11,'bold'),foreground='#245B86',spacing1=12,spacing3=4)
    keys=[]
    current=[topic if topic in TOPICS else 'quick']
    data=VI_DATA if language=='vi' else TOPICS
    def display(key):
        current[0]=key
        title,sections=data[key];body.configure(state='normal');body.delete('1.0','end')
        body.insert('end',title+'\n','title')
        for heading,text in sections:body.insert('end',heading+'\n','heading');body.insert('end',text+'\n\n')
        body.configure(state='disabled');body.yview_moveto(0)
    def selected(event=None):
        if topics.curselection():display(keys[topics.curselection()[0]])
    def refresh(*args):
        keys[:]=[k for k,v in data.items() if query.get().casefold() in str(v).casefold()]
        topics.delete(0,'end')
        for key in keys:topics.insert('end',data[key][0])
    query.trace_add('write',refresh);topics.bind('<<ListboxSelect>>',selected)
    close_button=ttk.Button(outer,command=close);close_button.pack(anchor='e',pady=(12,0))
    def change_language(event=None):
        nonlocal data
        vi=lang.get()=='Tiếng Việt';data=VI_DATA if vi else TOPICS;labels=VI_UI if vi else EN_UI
        window.title(labels['title']);title_label.configure(text=labels['title']);hint.configure(text=labels['hint'])
        search_label.configure(text=labels['search']);close_button.configure(text=labels['close'])
        query.set('');refresh()
        key=current[0];topics.selection_set(keys.index(key));topics.see(keys.index(key));display(key)
    selector.bind('<<ComboboxSelected>>',change_language);change_language()
    window._help_body=body;window._help_topics=topics;window._help_language=selector
    return window

def help_button(parent,topic,side='left'):
    import tkinter as tk
    button=tk.Button(parent,text='ⓘ',width=2,fg='#1565C0',activeforeground='#0D47A1',
                     relief='flat',cursor='hand2',font=('Segoe UI',12,'bold'),
                     command=lambda:show_help(parent.winfo_toplevel(),topic),takefocus=True)
    button.pack(side=side,padx=3);button.help_topic=topic
    return button

def write_guide(path,language='en'):
    data=VI_DATA if language=='vi' else TOPICS
    labels=VI_UI if language=='vi' else EN_UI
    nav=''.join(f'<a href="#{key}">{escape(title)}</a>' for key,(title,_) in data.items())
    sections=''.join(f'<section id="{key}"><h2>{escape(title)}</h2>'+''.join(f'<h3>{escape(h)}</h3><p>{escape(t).replace(chr(10),"<br>")}</p>' for h,t in parts)+'</section>' for key,(title,parts) in data.items())
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PIP User Guide</title><style>body{margin:0;background:#f4f7fa;color:#243647;font:16px/1.65 system-ui}header,main{max-width:1100px;margin:auto;padding:28px}header{background:#183c59;color:white}nav{display:flex;flex-wrap:wrap;gap:8px}nav a{background:white;color:#183c59;padding:7px 12px;border-radius:5px}section{background:white;padding:24px 32px;margin:18px 0;border-radius:8px;scroll-margin-top:20px}h2{color:#183c59}h3{margin-bottom:4px;color:#245b86}p{margin-top:4px}@media print{nav{display:none}body{background:white}section{break-inside:avoid;padding:10px 0}}</style><header><h1>PIP User Guide</h1><p>English · Daily scheduling, media preparation and QC</p></header><main><nav>'+nav+'</nav>'+sections+'</main></html>'
    html=html.replace('lang="en"',f'lang="{language}"').replace('PIP User Guide',labels['title']).replace(EN_UI['subtitle'],labels['subtitle'])
    other='GUIDE.html' if language=='vi' else 'GUIDE_VI.html'
    html=html.replace('<nav>',f'<nav><a href="{other}">Tiếng Việt / English</a>')
    Path(path).write_text(html,encoding='utf-8')
