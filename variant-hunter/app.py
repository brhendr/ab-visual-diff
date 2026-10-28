"""Variant Hunter: exploratory visual A/B-test detection."""
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
from PIL import Image, ImageChops, ImageEnhance
from playwright.sync_api import sync_playwright
from analysis import DOM_CAPTURE, compare_elements, summarize_groups, highlight_boxes

ROOT=Path(__file__).resolve().parent
RUNS=ROOT/'runs'
RUNS.mkdir(exist_ok=True)
st.set_page_config(page_title='Variant Hunter',page_icon='🔎',layout='wide')
st.title('🔎 Variant Hunter')
st.caption('Discover potentially different site experiences across independent visits. Differences are not proof of an experiment.')

def validate_url(value):
    value=value.strip()
    if not value.startswith(('https://','http://')):value='https://'+value
    parsed=urlparse(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Enter a valid public http(s) URL without credentials.')
    return value

def digest(image):
    pixels=list(image.convert('L').resize((17,16),Image.Resampling.LANCZOS).getdata())
    return ''.join('1' if pixels[row*17+col+1]>pixels[row*17+col] else '0' for row in range(16) for col in range(16))

def hamming(a,b):
    return sum(x!=y for x,y in zip(a,b))

def scan_visit(browser,url,index,folder,width,height,delay,full_page,disable_animations,ignore_media,scroll):
    ctx=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1,
                            locale='en-US',color_scheme='light',reduced_motion='reduce')
    page=ctx.new_page()
    item={'visit':index,'error':None}
    try:
        response=page.goto(url,wait_until='domcontentloaded',timeout=30000)
        item['status']=response.status if response else None
        if scroll:
            page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
            page.wait_for_timeout(600)
            page.evaluate('window.scrollTo(0,0)')
        if disable_animations:
            page.add_style_tag(content='*,*::before,*::after{animation-duration:0s!important;transition-duration:0s!important;caret-color:transparent!important}')
        page.wait_for_timeout(int(delay*1000))
        if ignore_media:
            page.evaluate("""() => {
                document.querySelectorAll('video').forEach(v => {try {v.pause()} catch (_) {}});
            }""")
            page.add_style_tag(content="""
                video, img[src*=".gif" i], picture source[srcset*=".gif" i] {
                    visibility: hidden !important;
                }
            """)
        item['final_url']=page.url
        item['title']=page.title()
        item['elements']=page.evaluate(DOM_CAPTURE)
        item['framework_hints']=page.evaluate("""() => ({
            Optimizely:!!window.optimizely,
            ABTasty:!!window.ABTasty,
            AdobeTarget:!!window.adobe?.target,
            VWO:!!window._vwo_code,
            GrowthBook:!!window.growthbook
        })""")
        item['image']=f'visit_{index:03}.png'
        page.screenshot(path=str(folder/item['image']),full_page=full_page,animations='disabled')
        with Image.open(folder/item['image']) as im:item['hash']=digest(im)
    except Exception as error:
        item['error']=str(error)
    finally:
        ctx.close()
    return item

def cluster(visits,threshold):
    groups=[]
    for visit in visits:
        if visit.get('error') or not visit.get('hash'):continue
        for group in groups:
            if hamming(visit['hash'],group[0]['hash'])<=threshold:
                group.append(visit)
                break
        else:groups.append([visit])
    return sorted(groups,key=len,reverse=True)

def run_scan(url,n,width,height,delay,full_page,animations,ignore_media,scroll,threshold,headless,restart):
    folder=RUNS/datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=True)
    progress=st.progress(0)
    message=st.empty()
    visits=[]
    with sync_playwright() as playwright:
        browser=None
        try:
            if not restart:browser=playwright.chromium.launch(headless=headless)
            for index in range(1,n+1):
                message.write(f'Visit {index} of {n}…')
                if restart:browser=playwright.chromium.launch(headless=headless)
                try:
                    visits.append(scan_visit(browser,url,index,folder,width,height,delay,full_page,animations,ignore_media,scroll))
                finally:
                    if restart:
                        browser.close()
                        browser=None
                progress.progress(index/n)
        finally:
            if browser:browser.close()
    groups=cluster(visits,threshold)
    report={'format_version':3,'url':url,'created_at':datetime.now(timezone.utc).isoformat(),
            'settings':{'visits':n,'viewport':[width,height],'settle_seconds':delay,'full_page':full_page,
                        'hash_threshold':threshold,'scroll_trigger':scroll,'ignore_moving_media':ignore_media,'restart_browser_per_visit':restart},
            'visits':visits,'groups':[[v['visit'] for v in g] for g in groups],
            'dom_comparisons':summarize_groups([[v['visit'] for v in g] for g in groups],{v['visit']:v for v in visits})}
    (folder/'report.json').write_text(json.dumps(report,indent=2))
    message.empty()
    progress.empty()
    return folder

with st.sidebar:
    st.header('Scan settings')
    raw=st.text_input('Website URL',placeholder='https://example.com')
    visits=st.slider('Independent visits',2,40,12)
    width=st.number_input('Viewport width (px)',320,2560,1440,step=80)
    height=st.number_input('Viewport height (px)',400,1600,900,step=50)
    wait=st.slider('Wait after page load (seconds)',1,15,4)
    full=st.checkbox('Capture full page',value=False)
    scroll=st.checkbox('Scroll down and back before capture',value=False)
    animations=st.checkbox('Disable CSS animations',value=True)
    ignore_media=st.checkbox('Exclude videos and animated GIFs',value=True,
        help='Pause and hide HTML video and GIFs without changing their layout. Canvas animations and embedded video frames may remain.')
    threshold=st.slider('Group similar images (hash distance)',0,80,15)
    restart=st.checkbox('Restart Chromium for every visit',value=False,
        help='Every visit already has fresh cookies and site storage. This additionally restarts the browser process.')
    headless=st.checkbox('Run browser in background',value=True)
    run=st.button('Run scan',type='primary',use_container_width=True)

if run:
    try:
        with st.spinner('Scanning…'):
            folder=run_scan(validate_url(raw),visits,int(width),int(height),wait,full,animations,ignore_media,scroll,threshold,headless,restart)
        st.session_state['last_folder']=str(folder)
    except Exception as error:st.error(f'Scan failed: {error}')

saved=sorted((p for p in RUNS.iterdir() if (p/'report.json').exists()),reverse=True)
if saved:
    with st.sidebar:
        st.divider()
        st.header('Saved scans')
        choices={f"{p.name} — {json.loads((p/'report.json').read_text()).get('url','')}":str(p) for p in saved}
        selected=st.selectbox('Open previous scan',list(choices))
        if st.button('Open selected scan'):
            st.session_state['last_folder']=choices[selected]
            st.rerun()

folder_name=st.session_state.get('last_folder')
if not folder_name:
    st.info('Enter a URL and run a scan. Evidence will be saved locally in the runs folder.')
    st.stop()
folder=Path(folder_name)
if not (folder/'report.json').exists():
    st.error('Saved scan is missing its report.json.')
    st.stop()
report=json.loads((folder/'report.json').read_text())
items=report['visits']
valid=[v for v in items if not v.get('error')]
by_id={v['visit']:v for v in items}
groups=[[by_id[i] for i in ids] for ids in report['groups']]
c1,c2,c3=st.columns(3)
c1.metric('Successful visits',f'{len(valid)} / {len(items)}')
c2.metric('Visual groups',len(groups))
c3.metric('Potential alternatives',max(len(groups)-1,0))
if not valid:st.error('No successful captures. Site automation may be blocked or the page may be unreachable.')
elif len(groups)==1:st.success('One visual group found. This does not rule out active experiments.')
else:st.warning('Multiple visual groups detected. Check for experiments versus dynamic page content.')
for v in items:
    if v.get('error'):st.caption(f"Visit {v['visit']}: {v['error']}")

st.subheader('Visual groups')
if groups:
    columns=st.columns(min(4,len(groups)))
    for i,g in enumerate(groups):
        with columns[i%len(columns)]:
            st.markdown(f'**Group {i+1}** — {len(g)} visit(s)')
            st.image(str(folder/g[0]['image']),use_container_width=True)
            st.caption('Visits: '+', '.join(str(x['visit']) for x in g))

if len(groups)>=2:
    st.subheader('Side-by-side comparison')
    labels=[f'Group {i+1} ({len(g)} visits)' for i,g in enumerate(groups)]
    a_col,b_col=st.columns(2)
    with a_col:aidx=st.selectbox('Left',range(len(groups)),format_func=lambda i:labels[i],index=0)
    with b_col:bidx=st.selectbox('Right',range(len(groups)),format_func=lambda i:labels[i],index=1)
    a_visit,b_visit=groups[aidx][0],groups[bidx][0]
    with Image.open(folder/a_visit['image']) as ia:a=ia.convert('RGB')
    with Image.open(folder/b_visit['image']) as ib:b=ib.convert('RGB')
    a_col.image(a,use_container_width=True)
    b_col.image(b,use_container_width=True)
    size=(480,360)
    pixel_difference=ImageChops.difference(a.resize(size),b.resize(size)).convert('RGB')
    changed=sum(1 for pixel in pixel_difference.getdata() if max(pixel)>35)
    st.write(f'**Approximate changed-pixel area:** {100*changed/(size[0]*size[1]):.1f}%')
    with st.expander('Show difference image'):
        dx=ImageChops.difference(a.resize((960,720)),b.resize((960,720)))
        st.image(ImageEnhance.Contrast(dx).enhance(3),use_container_width=True)

    st.subheader('Element-level changes')
    changes=compare_elements(a_visit.get('elements',[]),b_visit.get('elements',[]))
    if changes:
        st.metric('Changed matched elements',sum(c['type']=='modified' for c in changes))
        st.json([{'Type':c['type'],'Element':c['tag'],'Before':c['before'],
            'After':c['after'],'Fields':', '.join(c['fields'])} for c in changes],expanded=False)
        left,right=st.columns(2)
        left.image(highlight_boxes(a,changes,'a'),caption='Baseline: outlined changes',use_container_width=True)
        right.image(highlight_boxes(b,changes,'b'),caption='Alternative: outlined changes',use_container_width=True)
    else:st.info('No visible text/link/image differences in these representative visits.')
    with st.expander('Repeatability of changed text across visits'):
        for entry in report.get('dom_comparisons',[]):
            st.write(f"Group {entry['group']} vs Group {entry['compared_with']}")
            if entry['repeatable_changes']:st.json(entry['repeatable_changes'],expanded=False)
else:st.info('Two or more groups are required for DOM comparisons.')

st.subheader('Saved scan evidence')
st.caption('The screenshots, visible DOM snapshots and JSON report are stored locally. Download or reopen without rescanning.')
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in folder.iterdir():
        if path.is_file():archive.write(path,arcname=path.name)
st.download_button('Download full evidence ZIP',data=buffer.getvalue(),
    file_name=f'variant_hunter_{folder.name}.zip',mime='application/zip')
hints=sorted({k for v in valid for k,present in v.get('framework_hints',{}).items() if present})
st.write('**Detected runtime hints:** '+(', '.join(hints) if hints else 'none'))
st.download_button('Download scan JSON',data=json.dumps(report,indent=2),
    file_name='variant_hunter_report.json',mime='application/json')
st.caption(f'Saved locally: {folder}. All visits share the same public IP. Visual differences are not proof of an experiment.')
