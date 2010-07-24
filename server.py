#!/usr/bin/python
# -*- coding: latin-1 -*-
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation; either version 3, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTIBILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.

"Simple SOAP Server implementation"

# WARNING: EXPERIMENTAL PROOF-OF-CONCEPT IN EARLY DEVELOPMENT STAGE 
# TODO:
# * Refactory: cleanup and remove duplicates between server ad client 
# * Generalize harcoded code
# * Handle and Enforce SoapAction, namespaces, and exceptions
# * Generate a WSDL suitable for testing with SoapUI

__author__ = "Mariano Reingart (mariano@nsis.com.ar)"
__copyright__ = "Copyright (C) 2010 Mariano Reingart"
__license__ = "LGPL 3.0"
__version__ = "0.02"

from simplexml import SimpleXMLElement

DEBUG = False

class SoapFault(RuntimeError):
    def __init__(self,faultcode,faultstring):
        self.faultcode = faultcode
        self.faultstring = faultstring

# soap protocol specification & namespace
soap_namespaces = dict(
    soap11="http://schemas.xmlsoap.org/soap/envelope/",
    soap="http://schemas.xmlsoap.org/soap/envelope/",
    soapenv="http://schemas.xmlsoap.org/soap/envelope/",
    soap12="http://www.w3.org/2003/05/soap-env",
)

class SoapDispatcher(object):
    "Simple Dispatcher for SOAP Server"
    
    def __init__(self, name, documentation='', action='', location='', 
                 namespace=None, prefix=False, 
                 soap_uri="http://schemas.xmlsoap.org/soap/envelope/", 
                 soap_ns='soap',
                 **kwargs):
        self.methods = {}
        self.name = name
        self.documentation = documentation
        self.action = action # SoapAction
        self.location = location
        self.namespace = namespace # targetNamespace
        self.prefix = prefix
        self.soap_ns = soap_ns
        self.soap_uri = soap_uri
    
    def register_function(self, method, function, returns, args):
        self.methods[method] = function, returns, args
        
    def dispatch(self, xml):
        "Receive and proccess SOAP call"
        # default values:
        prefix = self.prefix
        ret = None
        fault = None
        soap_ns = self.soap_ns
        soap_uri = self.soap_uri
        soap_fault_code = 'Client'

        try:
            request = SimpleXMLElement(xml, namespace=self.namespace)

            # detect soap prefix and uri (attributes of Envelope)
            attrs = request.attributes()
            for k in attrs.keys():
                attr = attrs[k]
                if attr.value in ("http://schemas.xmlsoap.org/soap/envelope/",
                                  "http://www.w3.org/2003/05/soap-env",):
                    soap_ns = attr.localName
                    soap_uri = attr.value
                
            # parse request message and get local method
            
            method = request['%s:Body' % soap_ns].children()[0]
            prefix = method.getPrefix()
            if DEBUG: print "dispatch method", method.getName()
            function, returns_types, args_types = self.methods[method.getLocalName()]
        
            # de-serialize parameters
            args = method.children().unmarshall(args_types)
 
            soap_fault_code = 'Server'
            # execute function
            ret = function(**args)
            if DEBUG: print ret

        except Exception, e:
            etype, evalue, etb = sys.exc_info()
            if DEBUG or True: 
                import traceback
                detail = ''.join(traceback.format_exception(etype, evalue, etb))
            else:
                detail = None
            fault = {'faultcode': "%s.%s" % (soap_fault_code, etype.__name__), 
                     'faultstring': unicode(evalue), 
                     'detail': detail}

        # build response message
        if not prefix:
            xml = """<%(soap_ns)s:Envelope xmlns:%(soap_ns)s="%(soap_uri)s"/>"""  
        else:
            xml = """<%(soap_ns)s:Envelope xmlns:%(soap_ns)s="%(soap_uri)s"
                       xmlns:%(prefix)s="%(namespace)s"/>"""  
            
        xml = xml % {'namespace': self.namespace, 'prefix': prefix,
                     'soap_ns': soap_ns, 'soap_uri': soap_uri}
        print xml
        response = SimpleXMLElement(xml, namespace=self.namespace,
                                    prefix=prefix)

        body = response.addChild("%s:Body" % soap_ns, ns=False)
        if fault:
            # generate a Soap Fault (with the python exception)
            body = response.addChild("%s:Body" % soap_ns, ns=False)
            body.marshall("%s:Fault" % soap_ns, fault, ns=False)
        else:
            # return normal value
            res = body.addChild("%sResponse" % method.getLocalName(), 
                                 ns=method.getPrefix())
            # serialize returned values (response)
            res.marshall(returns_types.keys()[0], ret, )

        return response.asXML()

    # Introspection functions:

    def list_methods(self):
        "Return a list of aregistered operations"
        return [(method, function.__doc__) for method, (function, returns, args) in self.methods.items()] 

    def help(self, method=None):
        "Generate sample request and response messages"
        (function, returns, args) = self.methods[method]
        xml = """
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body><%(method)s xmlns="%(namespace)s"/></soap:Body>
</soap:Envelope>"""  % {'method':method, 'namespace':self.namespace}
        request = SimpleXMLElement(xml, namespace=self.namespace, prefix=self.prefix)
        for k,v in args.items():
            request[method].marshall(k, v, add_comments=True, ns=False)

        xml = """
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body><%(method)sResponse xmlns="%(namespace)s"/></soap:Body>
</soap:Envelope>"""  % {'method':method, 'namespace':self.namespace}
        response = SimpleXMLElement(xml, namespace=self.namespace, prefix=self.prefix)
        for k,v in returns.items():
            response['%sResponse'%method].marshall(k, v, add_comments=True, ns=False)

        return request.asXML(pretty=True), response.asXML(pretty=True), function.__doc__


    def wsdl(self):
        "Generate Web Service Description v1.1"
        xml = """<?xml version="1.0"?>
<wsdl:definitions name="%(name)s" 
          targetNamespace="%(namespace)s"
          xmlns:tns="%(namespace)s"
          xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
          xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
          xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <wsdl:documentation xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/">%(documentation)s</wsdl:documentation>

    <wsdl:types>
       <xsd:schema targetNamespace="%(namespace)s"
              elementFormDefault="qualified"
              xmlns:xsd="http://www.w3.org/2001/XMLSchema">
       </xsd:schema>
    </wsdl:types>

</wsdl:definitions>
""" % {'namespace': self.namespace, 'name': self.name, 'documentation': self.documentation}
        wsdl = SimpleXMLElement(xml)

        for method, (function, returns, args) in self.methods.items():
            # create elements:
                
            def parseElement(name, values, array=False, complex=False):
                if not complex:
                    element = wsdl['wsdl:types']['xsd:schema'].addChild('xsd:element')
                    complex = element.addChild("xsd:complexType")
                else:
                    complex = wsdl['wsdl:types']['xsd:schema'].addChild('xsd:complexType')
                    element = complex
                element.addAttribute('name', name)
                if not array:
                    all = complex.addChild("xsd:all")
                else:
                    all = complex.addChild("xsd:sequence")
                for k,v in values:
                    e = all.addChild("xsd:element")
                    e.addAttribute('name', k)
                    if array:
                        e.addAttribute('minOccurs',"0")
                        e.addAttribute('maxOccurs',"unbounded")
                    if v in (int, str, float, bool, unicode):
                        type_map={str:'xsd:string',bool:'xsd:boolean',int:'xsd:integer',float:'xsd:float',unicode:'xsd:string'}
                        t=type_map[v]
                    elif isinstance(v, list):
                        n="ArrayOf%s%s" % (name, k)
                        l = []
                        for d in v:
                            l.extend(d.items())
                        parseElement(n, l, array=True, complex=True)
                        t = "tns:%s" % n
                    elif isinstance(v, dict): 
                        n="%s%s" % (name, k)
                        parseElement(n, v.items(), complex=True)
                        t = "tns:%s" % n
                    e.addAttribute('type', t)
            
            parseElement("%s" % method, args.items())
            parseElement("%sResponse" % method, returns.items())

            # create messages:
            for m,e in ('Input',''), ('Output','Response'):
                message = wsdl.addChild('wsdl:message')
                message.addAttribute('name', "%s%s" % (method, m))
                part = message.addChild("wsdl:part")
                part.addAttribute('name', 'parameters')
                part.addAttribute('element', 'tns:%s%s' % (method,e))

        # create ports
        portType = wsdl.addChild('wsdl:portType')
        portType.addAttribute('name', "%sPortType" % self.name)
        for method in self.methods.keys():
            op = portType.addChild('wsdl:operation')
            op.addAttribute('name', method)
            input = op.addChild("wsdl:input")
            input.addAttribute('message', "tns:%sInput" % method)
            output = op.addChild("wsdl:output")
            output.addAttribute('message', "tns:%sOutput" % method)

        # create bindings
        binding = wsdl.addChild('wsdl:binding')
        binding.addAttribute('name', "%sBinding" % self.name)
        binding.addAttribute('type', "tns:%sPortType" % self.name)
        soapbinding= binding.addChild('soap:binding')
        soapbinding.addAttribute('style',"document")
        soapbinding.addAttribute('transport',"http://schemas.xmlsoap.org/soap/http")
        for method in self.methods.keys():
            op = binding.addChild('wsdl:operation')
            op.addAttribute('name', method)
            soapop = op.addChild('soap:operation')
            soapop.addAttribute('soapAction', self.action)
            soapop.addAttribute('style', 'document')
            input = op.addChild("wsdl:input")
            ##input.addAttribute('name', "%sInput" % method)
            soapbody = input.addChild("soap:body")
            soapbody.addAttribute("use","literal")
            output = op.addChild("wsdl:output")
            ##output.addAttribute('name', "%sOutput" % method)
            soapbody = output.addChild("soap:body")
            soapbody.addAttribute("use","literal")

        service = wsdl.addChild('wsdl:service')
        service.addAttribute("name", "%sService" % self.name)
        service.addChild('wsdl:documentation', text=self.documentation)
        port=service.addChild('wsdl:port')
        port.addAttribute("name","%s" % self.name)
        port.addAttribute("binding","tns:%sBinding" % self.name)
        soapaddress = port.addChild('soap:address')
        soapaddress.addAttribute("location", self.location)
        return wsdl.asXML(pretty=True)
    

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
class SOAPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        "User viewable help information and wsdl"
        args = self.path[1:].split("?")
        print "serving", args
        if self.path != "/" and args[0] not in self.server.dispatcher.methods.keys():
            self.send_error(404, "Method not found: %s" % args[0])
        else:
            if self.path == "/":
                # return wsdl if no method supplied
                response = self.server.dispatcher.wsdl()
            else:
                # return supplied method help (?request or ?response messages)
                req, res, doc = self.server.dispatcher.help(args[0])
                if len(args)==1 or args[1]=="request":
                    response = req
                else:
                    response = res                
            self.send_response(200)
            self.send_header("Content-type", "text/xml")
            self.end_headers()
            self.wfile.write(response)

    def do_POST(self):
        "SOAP POST gateway"
        self.send_response(200)
        self.send_header("Content-type", "text/xml")
        self.end_headers()
        request = self.rfile.read(int(self.headers.getheader('content-length')))
        response = self.server.dispatcher.dispatch(request)
        self.wfile.write(response)


if __name__=="__main__":
    import sys

    dispatcher = SoapDispatcher(
        name = "PySimpleSoapSample",
        location = "http://localhost:8008/",
        action = 'http://localhost:8008/', # SOAPAction
        namespace = "http://example.com/pysimplesoapsamle/", prefix="ns0",
        documentation = 'Example soap service using PySimpleSoap',
        trace = True,
        ns = True)
    
    def adder(p,c):
        print c[0]['d'],c[1]['d'],
        return {'ab': p['a']+p['b'], 'dd': c[0]['d']+c[1]['d']}

    def dummy(in0):
        return in0

    dispatcher.register_function('Adder', adder,
        returns={'AddResult': {'ab': int, 'dd': str } }, 
        args={'p': {'a': int,'b': int}, 'c': [{'d': str}]})

    dispatcher.register_function('Dummy', dummy,
        returns={'out0': str}, 
        args={'in0': str})

    if '--local' in sys.argv:

        wsdl=dispatcher.wsdl()
        print wsdl
        open("C:/test.wsdl","w").write(wsdl)
        # dummy local test (clasic soap dialect)
        xml = """<?xml version="1.0" encoding="UTF-8"?> 
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
       <soap:Body>
         <Adder xmlns="http://example.com/sample.wsdl">
           <p>
            <a>1</a>
            <b>2</b>
           </p>
           <c>
            <d>hola</d>
            <d>chau</d>
           </c>
        </Adder>
       </soap:Body>
    </soap:Envelope>"""

        print dispatcher.dispatch(xml)

        # dummy local test (modern soap dialect, SoapUI)
        xml = """
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:pys="http://example.com/pysimplesoapsamle/">
   <soapenv:Header/>
   <soapenv:Body>
      <pys:Adder>
         <!--You may enter the following 2 items in any order-->
         <pys:p>
            <!--You may enter the following 2 items in any order-->
            <!--type: integer-->
            <pys:a>9</pys:a>
            <!--type: integer-->
            <pys:b>3</pys:b>
         </pys:p>
         <pys:c>
            <!--Zero or more repetitions:-->
            <!--type: string-->
            <pys:dx>foo</pys:dx>
            <pys:d></pys:d>
         </pys:c>
      </pys:Adder>
   </soapenv:Body>
</soapenv:Envelope>
    """
    
        print dispatcher.dispatch(xml)

        for method, doc in dispatcher.list_methods():
            request, response, doc = dispatcher.help(method)
            ##print request
            ##print response
            
    if '--serve' in sys.argv:
        print "Starting server..."
        httpd = HTTPServer(("", 8008), SOAPHandler)
        httpd.dispatcher = dispatcher
        httpd.serve_forever()

    if '--consume' in sys.argv:
        from client import SoapClient
        client = SoapClient(
            location = "http://localhost:8008/",
            action = 'http://localhost:8008/', # SOAPAction
            namespace = "http://example.com/sample.wsdl", 
            soap_ns='soap',
            trace = True,
            ns = False)
        response = client.Adder(p={'a':1,'b':2},c=[{'d':'hola'},{'d':'chau'}])
        result = response.AddResult
        print int(result.ab)
        print str(result.dd)

