#!/bin/env python

import requests
import simplejson as json
import sys
import datetime
import time



logThreshold=1 #INFO
repeatsMax=100
connurl='http://localhost:9200'
termWhite=True
if len(sys.argv)>1:

    for arg in sys.argv:
        if arg.startswith('-c='):
            connurl=arg[3:]
            if not connurl.startswith('http://'): connurl = 'http://'+connurl

        if arg.startswith('-l='):
            if   arg[3:]=="DEBUG":logThreshold=0
            elif arg[3:]=="WARNING":logThreshold=2
            elif arg[3:]=="ERROR":logThreshold=3
            elif arg[3:]=="FATAL":logThreshold=4

        if arg.startswith('-r='):
            repeatsMax=int(arg[3:])

        if arg.startswith('-t='):
            if arg[3:].lower()=='black':termWhite=False

else:
    print "Usage: . logprint.py -c=%URL -l=%[DEBUG,INFO,WARNING,ERROR,FATAL] -r=%[-1,0,...] -t=%[white,black]"
    print " -c: connection URL (default: http://localhost:9200)"
    print " -l: log level threshold (default: INFO)"
    print " -r: DEBUG/INFO repeat suppression threshold (default: 100, disable: -1)"
    print " -t: your terminal background color (default: white)"
    print "\n Starting logger using default values..."

#url =  'http://localhost:9200/run*/cmsswlog/_search'
url =  connurl+'/run*/cmsswlog/_search'

#resp = requests.post(url, query)

addSpace=False
repeatsMax=100
suppressionMap = {}
alreadySuppressed = {}

filter1 =  { "range": {
               "_timestamp": {
                 "from": "",
                 "to": ""
               }
#               ,"severityVal" : { "gte" :  str(logThreshold+1)}
             }
           }
         


filter2 =  { "and" : [
               {"range": {
                 "_timestamp": {
                   "from": "",
                   "to": ""
                 }
               }},
               {"range": {
                 "severityVal" : { "gte" :  str(logThreshold)}
               }}
             ]
           }
               #,{"or": [{"term":{"severity":"INFO"}},{"term":{"severity":"WARNINIG"}},{"term":{"severity":"ERROR"}},{"term":{"severity":"FATAL"}}] }
               #,{"not":{"term":{"severity":"DEBUG"}}}



qdoc = { 
  "fields":["_timestamp", "_source"], 
  "size":100, 
  "query": { 
    "filtered": {"query": {"match_all": {}}
#      "filter": {
#        "range": {
#          "_timestamp": {
#            "from": "",
#            "to": ""
#          }
#        }
#      }
    }
  },
  "sort": { "_timestamp": { "order": "asc" }}
}

if logThreshold==0:
    useFilters2=False
    qdoc['query']['filtered']['filter'] = filter1
else:
    useFilters2=True
    qdoc['query']['filtered']['filter'] = filter2

sleept = 0.5

init = True

#2 seconds delay
tnow =  datetime.datetime.utcnow().isoformat()
time.sleep(sleept)
tfuture =  datetime.datetime.utcnow().isoformat()
time.sleep(sleept)
lastEmpty=True

counter=0

while True:

    counter+=1
    tbefore = tnow
    tnow = tfuture
    tfuture = datetime.datetime.utcnow().isoformat()

    if lastEmpty==False:
        print "\n================\n"

    time.sleep(sleept)

    if useFilters2:
        qdoc['query']['filtered']['filter']['and'][0]['range']['_timestamp']['from']=tbefore
        qdoc['query']['filtered']['filter']['and'][0]['range']['_timestamp']['to']=tnow
    else:
        qdoc['query']['filtered']['filter']['range']['_timestamp']['from']=tbefore
        qdoc['query']['filtered']['filter']['range']['_timestamp']['to']=tnow
    q = json.dumps(qdoc)


    resp = requests.post(url, q)
    data = json.loads(resp.content)
    lastEmpty==True
    maxhostlen=0
   
    #allow suppressed messages every 60 seconds
    if counter%(60/sleept)==0:
        for k in suppressionMap.keys():
            if suppressionMap[k]>100:
                suppressionMap[k]=99
            elif suppressionMap[k]>0:
                suppressionMap[k]-=1

    try:
      if data['hits']['total']!=0:
        lastEmpty==False

        arr = data['hits']['hits']

        for e in arr:


            runstring = ''
            try:
	        runidx = e['_index'].split('_')
                if runidx[0].startswith('log_'):
                    rn = runidx[1]
                else:
                    rn = runidx[0]
                if rn[3:].isdigit():
                    runstring = 'Run: '+str(int(rn[3:]))+' '
            except:
                pass


            ev = e['_source']
            severity = ev['severity']

            #suppression
            repeats=0
            if repeatsMax!=-1:
              try:
                rep = suppressionMap[ev['lexicalId']]
                rep+=1
                suppressionMap[ev['lexicalId']]=rep
                repeats=rep
                if repeats>repeatsMax and (severity=="INFO" or severity=="DEBUG"):
                    alreadySuppressed[ev['lexicalId']]=True
                    continue
              except:
                try:
                    suppressionMap[ev['lexicalId']]=1
                    repeats=1
                except:pass

            severity = ev['severity']
            sevorig=severity
            if severity=='INFO':
                #severity = '\x1b[32m INFO \x1b[0m'
                severity = '\x1b[37;1;42m INFO \x1b[0m   '
            if severity=='WARNING':
                severity = '\x1b[37;1;43m WARNING \x1b[0m'
            if severity=='ERROR':
                severity = '\x1b[37;1;41m ERROR \x1b[0m  '
            if severity=='FATAL':
                severity = '\x1b[31;1;40m FATAL \x1b[0m  '

            #msg time/zone are not present in all messages...
            msgtime=''
            try:
                msgtime = '\x1b[1m'+ev['msgtime']
                try:
                    msgtime+=' '+ev['msgtimezone']
                except:
                    pass
                msgtime+='\x1b[0m'
            except:
                pass
            host = ev['host']
            hlen = len(host)
            if hlen<maxhostlen and maxhostlen<30:
                host = host.ljust(maxhostlen-hlen)
            else:
                maxhostlen=hlen
               
            pidstr=('(pid '+str(ev['pid'])+')').ljust(11)
            #while len(pidstr)<7:
            #    pidstr+=' '

            #parse optional entries
            cat=''
            str2='\x1b[1m'
            try:
                cat =ev['category']
                str2 +=cat.ljust(21)+' '
            except:
                pass

            mod=''
            try:
                mod = ev['module']
                if mod!=cat:
                    str2+=' '+mod
            except:pass
            try:
                str2+=' '+ev['moduleInstance']
            except:pass
            try:
                str2+=' '+ev['moduleCall']
            except:pass
            try:
                str2+=' '+ev['fwkState']
            except:pass
            try:
                str2+='   \x1b[0mLumi:'+ str(ev['lumi'])
            except:pass
            try:
                str2+='   \x1b[0mEvent:'+str( ev['eventInPrc'])
            except:pass

            #construct final log print:
            str2+='\x1b[0m'
            if sevorig=='INFO':
                if termWhite:
                    print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  \x1b[47m'+ev['message']+'\x1b[0m'
                else:
                    print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  \x1b[41m'+ev['message']+'\x1b[0m'
            elif sevorig=='WARNING':
                print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  \x1b[37;1;45m'+ev['message']+'\x1b[0m'
            elif sevorig=='ERROR':
                print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  \x1b[37;1;40m'+ev['message']+'\x1b[0m'
            elif sevorig=='FATAL':
                print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  \x1b[31;1;40m'+ev['message']+'\x1b[0m'
            else:#debug
                print severity + runstring +' '+msgtime+' '+host+' '+pidstr+' : ' + str2 + '\n  '+ev['message']

            if repeats==repeatsMax and (sevorig=="INFO" or sevorig=="DEBUG"):
                try:
                    suppressionStatus = alreadySuppressed[ev['lexicalId']]
                except:
                    print "\x1b[1;36;46m[Printed message has reached maximum repeat threshold (",str(repeatsMax),") and will be suppressed for this session!]\x1b[0m"
            if addSpace:
                print ""
        #print json.dumps(data['hits']['hits'],indent=1)
    except Exception,ex:
      #print ex
      pass
