#!/usr/bin/env python3
"""Free in-scope topic discovery. Shared 24-hour cache, not exact search volume."""
import json,os,re,time,xml.etree.ElementTree as ET
from urllib import request,parse
BASE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(BASE,'topic_demand_cache.json')
POLICY=json.load(open(os.path.join(BASE,'content_policy.json')))
now=time.time()
if os.path.exists(CACHE):
    try:
        cached=json.load(open(CACHE))
        if cached.get('policy_version')==POLICY['version'] and now-cached.get('generated_at',0)<86400:
            cached['cache_hit']=True
            print(json.dumps(cached,ensure_ascii=False,indent=1));raise SystemExit(0)
    except (ValueError,KeyError):pass
UA={'User-Agent':'Mozilla/5.0'}
def get(url):
    with request.urlopen(request.Request(url,headers=UA),timeout=12) as r:return r.read().decode(errors='replace')
queries={
 'ai_updates':'(ChatGPT OR OpenAI OR Claude OR Gemini OR "AI Studio" OR Grok OR DeepSeek OR Qwen) (update OR launch OR features OR release) when:7d',
 'gadget_reviews':'(smartphone OR laptop OR earbuds OR tablet OR smartwatch) (review OR comparison OR "buying guide") when:7d',
 'personal_finance':'("personal finance" OR savings OR budgeting OR "credit card" OR "interest rates") when:7d'
}
out={'policy_version':POLICY['version'],'generated_at':now,'cache_hit':False,'priority':POLICY['priority'],'news_candidates':{},'search_trend_matches':[],'note':'RSS coverage and Google Trends trending matches are demand proxies, NOT exact keyword search volumes. Verify official primary sources and competition for finalists. Prefer AI platform updates.'}
for pillar,q in queries.items():
    try:
        xml=get('https://news.google.com/rss/search?'+parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'}))
        items=[]
        for it in ET.fromstring(xml).iter('item'):
            items.append({'headline':it.findtext('title') or '', 'source':it.findtext('source') or '', 'url':it.findtext('link') or '', 'at':it.findtext('pubDate') or ''})
            if len(items)>=6:break
        out['news_candidates'][pillar]=items
    except Exception as e:out['news_candidates'][pillar]={'error':str(e)[:120]}
try:
    xml=get('https://trends.google.com/trending/rss?geo=US')
    pat=r'chatgpt|openai|claude|gemini|grok|deepseek|qwen|ai studio|iphone|pixel|samsung|laptop|earbud|personal finance|savings|mortgage|interest rate'
    for it in ET.fromstring(xml).iter('item'):
        title=it.findtext('title') or ''
        if re.search(pat,title,re.I):
            out['search_trend_matches'].append({'term':title,'url':it.findtext('link') or '', 'at':it.findtext('pubDate') or ''})
except Exception as e:out['trends_error']=str(e)[:120]
tmp=CACHE+'.tmp';json.dump(out,open(tmp,'w'),ensure_ascii=False,indent=1);os.replace(tmp,CACHE)
print(json.dumps(out,ensure_ascii=False,indent=1))
