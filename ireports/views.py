__author__ = 'jblowe'

from os import path, listdir

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseRedirect
from django import forms

from operator import itemgetter

from common.utils import loginfo
from common import cspace # we use the config file reading function
from cspace_django_site import settings
from cspace_django_site.main import cspace_django_site
from .models import AdditionalInfo

mainConfig = cspace_django_site.getConfig()

config = cspace.getConfig(path.join(settings.BASE_DIR, 'config'), 'ireports')

JRXMLDIRPATTERN = config.get('connect', 'JRXMLDIRPATTERN')

from xml.etree.ElementTree import tostring, parse, Element, fromstring

TITLE = 'iReports Available'

@login_required()
def enumerateReports():
    files = listdir("jrxml")

    jrxmlfiles = []
    for f in files:
        if '.jrxml' in f:
            jrxmlfiles.append(f)
    return jrxmlfiles


def getReportparameters(filename):
    parms = {}
    csidParms = True
    fileFound = False
    try:
        reportXML = parse(JRXMLDIRPATTERN % filename)
        fileFound = True
        parameters = reportXML.findall('{http://jasperreports.sourceforge.net/jasperreports}parameter')
        #print 'parameters',parameters
        for p in parameters:
            name = p.attrib['name']
            isForPrompting = p.get('isForPrompting')
            if name == 'csid':
                csidParms = False
            try:
                default = p.find('{http://jasperreports.sourceforge.net/jasperreports}defaultValueExpression').text
            except:
                default = ''
            try:
                description = p.find('{http://jasperreports.sourceforge.net/jasperreports}parameterDescription').text
            except:
                description = ''
            parms[name] = [default.strip('"'), isForPrompting, description.strip('"')]
    except:
        #raise
        # indicate that .jrxml file was not found...
        loginfo('ireports','jrxml file not found, no parms extracted.', {}, {})
    return parms,csidParms,fileFound


def makePayload(parms):
    """
    this method takes a dictionary of parameters and inserts them into the XML payload
    which is POSTed to the report service.
    :param parms: a dict of parameters and values for the iReport
    :return: string, XML doc really, containing payload with parameters
    """
    result = fromstring('''<?xml version="1.0"?>
<ns2:invocationContext xmlns:ns2="http://collectionspace.org/services/common/invocable"
     xmlns:ns3="http://collectionspace.org/services/jaxb">
    <mode>nocontext</mode>
    <docType>CollectionObjectTenant15</docType>
    <params/>
</ns2:invocationContext>''')
    p = result.find('params')
    for k, v in parms:
        e   = Element('param')
        key = Element('key')
        val = Element('value')
        key.text = k
        val.text = v
        e.append(key)
        e.append(val)
        p.append(e)
    return tostring(result)


def fileNamereplace(param, param1):
    pass


@login_required()
def index(request):
    connection = cspace.connection.create_connection(mainConfig, request.user)
    (url, data, statusCode, elapsedtime) = connection.make_get_request('cspace-services/reports')
    reportXML = fromstring(data)
    reportCsids = []
    reportNames = []
    for r in reportXML.findall('.//list-item'):
        reportCsids.append(r.find('csid').text)
        try:
            reportNames.append(r.find('name').text)
        except:
            reportNames.append('Name unknown')
    fileNames = []
    #print reportCsids
    for csid in reportCsids:
        try:
            (url, data, statusCode, elapsedtime) = connection.make_get_request('cspace-services/reports/%s' % csid)
            reportXML = fromstring(data)
            fileName = reportXML.find('.//filename')
            fileName = fileName.text
            fileName = fileName.replace('.jasper','.jrxml')
            parms,displayReport,fileFound = getReportparameters(fileName)
            fileName = fileName if displayReport else 'CSpace only'
            fileName = fileName if fileFound else 'Found in CSpace, not configured for this webapp'
            fileNames.append(fileName)
            #print fileName
        except:
            fileNames.append('Error getting report payload from CSpace: %s' % csid)
    reportData = list(zip(reportCsids, reportNames, fileNames))
    reportData = sorted(reportData, key=itemgetter(1))
    context = {'reportData': reportData, 'labels': 'name file'.split(' '), 'apptitle': TITLE}
    context['additionalInfo'] = AdditionalInfo.objects.filter(live=True)
    return render(request, 'listReports.html', context)


@login_required()
def ireport(request, report_csid):

    form = forms.Form()

    # get the report metadata for this report
    connection = cspace.connection.create_connection(mainConfig, request.user)
    (url, data, statusCode, elapsedtime) = connection.make_get_request('cspace-services/reports/%s' % report_csid)
    if data is None or statusCode not in (200, 201):
        error = 'status: %s' % statusCode
    else:
        error = None
        reportXML = fromstring(data)
        fileName = reportXML.find('.//filename')
        fileName = fileName.text
        fileName = fileName.replace('.jasper','.jrxml')
        outputMIME = reportXML.find('.//outputMIME').text
        name = reportXML.find('.//name').text

        if request.method == 'POST':
            form = forms.Form(request.POST)

            if form.is_valid():
                # run the report
                parms = [[p,request.POST[p]] for p in request.POST]
                payload = makePayload(parms)
                connection = cspace.connection.create_connection(mainConfig, request.user)
                (url, data, csid, elapsedtime) = connection.postxml(uri='cspace-services/reports/%s' % report_csid,
                                                                    requesttype='POST', payload=payload.decode('utf-8'))
                response = HttpResponse(data, content_type=outputMIME)
                return response
        else:
            # for now, we have to get the parms by reading and parsing the .jrxml file ourselves
            parms,displayReport,fileFound = getReportparameters(fileName)
            for p in parms:
                if str(parms[p][1]) == 'false':
                    form.fields[p] = forms.CharField(initial=parms[p][0], widget=forms.widgets.HiddenInput(), required=True)
                else:
                    form.fields[p] = forms.CharField(initial=parms[p][0], help_text=parms[p][2], required=True)

    return render(request, 'getReportParms.html',  {'report_csid': report_csid, 'form': form, 'report': name, 'apptitle': TITLE, 'error': error})
