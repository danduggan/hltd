#!/bin/env python

import sys,traceback
import os

import logging
import _inotify as inotify
import threading
import Queue

import elasticBand

from hltdconf import *
from aUtils import *

class elasticCollector():
    stoprequest = threading.Event()
    emptyQueue = threading.Event()
    source = False
    infile = False
    
    def __init__(self, esDir, inMonDir):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.esDirName = esDir
        self.inputMonDir = inMonDir
        #self.movedModuleLegend = False
        #self.movedPathLegend = False

    def start(self):
        self.run()

    def stop(self):
        self.stoprequest.set()

    def run(self):
        self.logger.info("Start main loop") 
        while not (self.stoprequest.isSet() and self.emptyQueue.isSet()) :
            if self.source:
                try:
                    event = self.source.get(True,0.5) #blocking with timeout
                    self.eventtype = event.mask
                    self.infile = fileHandler(event.fullpath)
                    self.emptyQueue.clear()
                    self.process() 
                except (KeyboardInterrupt,Queue.Empty) as e:
                    self.emptyQueue.set()
                except Exception as ex:
                    self.logger.exception(ex)
                    self.logger.fatal("Exiting on unhandled exception")
                    os._exit(1)
            else:
                time.sleep(0.5)

        es.flushAll()
        self.logger.info("Stop main loop")


    def setSource(self,source):
        self.source = source

    def process(self):
        self.logger.debug("RECEIVED FILE: %s " %(self.infile.basename))
        infile = self.infile
        filetype = infile.filetype
        eventtype = self.eventtype    
        if eventtype & (inotify.IN_CLOSE_WRITE | inotify.IN_MOVED_TO) :
            if filetype in [FAST,SLOW,QSTATUS]:
                self.elasticize()
            elif self.esDirName in infile.dir:
                if filetype in [INDEX,STREAM,OUTPUT,STREAMDQMHISTOUTPUT,STREAMERR]:self.elasticize()
                elif filetype in [EOLS]:self.elasticizeLS()
                elif filetype in [COMPLETE]:
                    self.elasticize()
                    self.stop()
                elif filetype == FLUSH:
                    self.logger.debug('FLUSH')
                    es.flushAllLS()
            elif filetype in [MODULELEGEND]:# and self.movedModuleLegend == False:
                try:
                  if not self.infile.basename.endswith(".jsn"):
                    if not os.path.exists(self.inputMonDir+'/microstatelegend.leg') and os.path.exists(self.inputMonDir):
                        self.infile.moveFile(self.inputMonDir+'/microstatelegend.leg',silent=True,createDestinationDir=False)
                  else:
                    if not os.path.exists(self.inputMonDir+'/microstatelegend.jsn') and os.path.exists(self.inputMonDir):
                        self.infile.moveFile(self.inputMonDir+'/microstatelegend.jsn',silent=True,createDestinationDir=False)
                except Exception,ex:
                    logger.error(ex)
                    pass
            elif filetype in [PATHLEGEND]:# and self.movedPathLegend == False:
                try:
                  if not self.infile.basename.endswith(".jsn"):
                    if not os.path.exists(self.inputMonDir+'/pathlegend.leg') and os.path.exists(self.inputMonDir):
                        self.infile.moveFile(self.inputMonDir+'/pathlegend.leg',silent=True,createDestinationDir=False)
                  else:
                    if not os.path.exists(self.inputMonDir+'/pathlegend.jsn') and os.path.exists(self.inputMonDir):
                        self.infile.moveFile(self.inputMonDir+'/pathlegend.jsn',silent=True,createDestinationDir=False)
                except Exception,ex:
                    logger.error(ex)
                    pass
            elif filetype == INI:
                destname = os.path.join(self.inputMonDir,infile.run+'_'+infile.ls+'_'+infile.stream+'_mon.ini')
                try:
                    if not os.path.exists(destname):
                        infile.moveFile(destname,silent=True,createDestinationDir=False)
                except Exception,ex:
                    logger.error(ex)
                    pass




    def elasticize(self):
        infile = self.infile
        filetype = infile.filetype
        name = infile.name
        if es and os.path.isfile(infile.filepath):
            if filetype == FAST: 
                es.elasticize_prc_istate(infile)
                self.logger.debug(name+" going into prc-istate")
            elif filetype == SLOW: 
                es.elasticize_prc_sstate(infile)
                self.logger.debug(name+" going into prc-sstate")
                self.infile.deleteFile(silent=True)  
            elif filetype == INDEX: 
                self.logger.info(name+" going into prc-in")
                es.elasticize_prc_in(infile)
                self.infile.deleteFile(silent=True)
            elif filetype == STREAM:
                self.logger.info(name+" going into prc-out")
                es.elasticize_prc_out(infile)
                self.infile.deleteFile(silent=True)
            elif filetype in [OUTPUT,STREAMDQMHISTOUTPUT,STREAMERR]:
                self.logger.info(name+" going into fu-out")
                es.elasticize_fu_out(infile)
                self.infile.deleteFile(silent=True)
            elif filetype == QSTATUS:
                self.logger.debug(name+" going into qstatus")
                es.elasticize_queue_status(infile)
            elif filetype == COMPLETE:
                self.logger.info(name+" going into fu-complete")
                dt=os.path.getctime(infile.filepath)
                completed = datetime.datetime.utcfromtimestamp(dt).isoformat()
                es.elasticize_fu_complete(completed)
                self.infile.deleteFile(silent=True)
                self.stop()
 

    def elasticizeLS(self):
        ls = self.infile.ls
        es.flushLS(ls)
        self.infile.deleteFile(silent=True)



if __name__ == "__main__":

    import procname
    procname.setprocname('elastic')

    conf=initConf()
    logging.basicConfig(filename=os.path.join(conf.log_dir,"elastic.log"),
                    level=conf.service_log_level,
                    format='%(levelname)s:%(asctime)s - %(funcName)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(os.path.basename(__file__))

    #STDOUT AND ERR REDIRECTIONS
    sys.stderr = stdErrorLog()
    sys.stdout = stdOutLog()


    #signal.signal(signal.SIGINT, signalHandler)
    
    eventQueue = Queue.Queue()

    dirname = sys.argv[1]
    inmondir = sys.argv[2]
    expected_processes = int(sys.argv[3])
    indexSuffix = conf.elastic_cluster
    update_modulo=conf.fastmon_insert_modulo
    rundirname = os.path.basename(os.path.normpath(dirname))
    monDir = os.path.join(dirname,"mon")
    tempDir = os.path.join(dirname,ES_DIR_NAME)


    #find out total number of logical cores
    pnproc = subprocess.Popen("nproc",shell=True, stdout=subprocess.PIPE)
    pnproc.wait()
    try:
      nlogical = int(pnproc.stdout.read())
    except:
      logger.warning('unable to run nproc command')
      nlogical=0
    nprocid = str(nlogical) + '_' + str(int(nlogical -round(nlogical*(1. - conf.resource_use_fraction))))

    monMask = inotify.IN_CLOSE_WRITE | inotify.IN_MOVED_TO
    tempMask = inotify.IN_CLOSE_WRITE | inotify.IN_MOVED_TO

    logger.info("starting elastic for "+rundirname[:3]+' '+rundirname[3:])

    try:
        os.makedirs(monDir)
    except OSError:
        pass
    try:
        os.makedirs(tempDir)
    except OSError:
        pass

    mr = None
    try:
        #starting inotify thread
        mr = MonitorRanger()
        mr.setEventQueue(eventQueue)
        mr.register_inotify_path(monDir,monMask)
        mr.register_inotify_path(tempDir,tempMask)
        mr.start_inotify()

        es = elasticBand.elasticBand('http://'+conf.es_local+':9200',rundirname,indexSuffix,expected_processes,update_modulo,nprocid)

        #starting elasticCollector thread
        ec = elasticCollector(ES_DIR_NAME,inmondir)
        ec.setSource(eventQueue)
        ec.start()

    except Exception as e:
        logger.exception(e)
        print traceback.format_exc()
        logger.error("when processing files from directory "+dirname)

    logging.info("Closing notifier")
    if mr is not None:
      mr.stop_inotify()

    logging.info("Quit")
    sys.exit(0)
