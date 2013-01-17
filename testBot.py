#!/usr/bin/python
# -*- coding: utf-8 -*-

from jabberbot import JabberBot, botcmd

import datetime, sys
import json
import logging
import re
import threading
import time
import urllib2
try:
    import xmpp
except ImportError:
    print >> sys.stderr, """
    You need to install xmpppy from http://xmpppy.sf.net/.
    On Debian-based systems, install the python-xmpp package.
    """
    sys.exit(-1)

current_status = {
    'jsession_id': None,
    'queue': None,
    'all_res_info': None,
    'main_course': None,
    'res_id': None,
    'full_res_info': None,
    'repick_user': {},
    'ordered_user': {},
    'latest_working_jsid': "E12D94968C63A09D354C294460F641B7",
}

#
users = {
}

class SystemInfoJabberBot(JabberBot):

    def __init__( self, jid, password, res = None, server=None, port=None):
        super( SystemInfoJabberBot, self).__init__( jid, password, res, server=server, port=port)
        # create console handler
        chandler = logging.StreamHandler()
        # create formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        # add formatter to handler
        chandler.setFormatter(formatter)
        # add handler to logger
        self.log.addHandler(chandler)
        # set level to INFO
        self.log.setLevel(logging.INFO)
        self.users = [""]
        self.message_queue = []
        self.thread_killed = False

    @botcmd
    def serverinfo( self, mess, args):
        """Displays information about the server"""
        version = open('/proc/version').read().strip()
        loadavg = open('/proc/loadavg').read().strip()
        return '%s\n\n%s' % ( version, loadavg, )

    @botcmd
    def time( self, mess, args):
        """Displays current server time"""
        return str(datetime.datetime.now())

    @botcmd
    def whoami(self, mess, args):
        """Tells you your username"""
        return mess.getFrom().getStripped()

    @botcmd
    def _res(self, mess, args):
    	'''Get today's restaurant info and recommanded menu.'''
        print "_res activated"
        queue = self._get_queue()
        main_course_dict = self._get_main_course()
        main_courses_string = "\n".join(main_course_dict[queue[0][1]])
        print main_courses_string
        return "%s\n %s" % (self._get_restaurant_info_in_queue(0),\
            main_courses_string)

    @botcmd
    def _menu(self, mess, args):
    	'''Get today's recommanded menu.'''
        print "_menu activated"
        queue = self._get_queue()
        main_course_dict = self._get_main_course() 
        main_courses_string = "\n".join(main_course_dict[queue[0][1]])
        print main_courses_string
        return main_courses_string

    @botcmd
    def _repick(self, mess, args):
        print "_repick activated"

        jid = mess.getFrom().getStripped()
        #if jid not in users:
        #    return "Sorry. You are not in the upwlabs lunch group. Ask someone in that group to order for you."

        if jid in current_status['repick_user']:
            return "Already repicked. Current repick: %d/6." % len(current_status['repick_user'])
        else:
            current_status['repick_user'][jid] = True
            if len(current_status['repick_user']) >= len(users) / 2:
                self._do_repick(mess, args)
            else:
                return "Repick submitted. Current repick: %d/6." % len(current_status['repick_user'])

    @botcmd(hidden=True)
    def _do_repick(self, mess, args):
        queue = self._get_queue()
        current_status['queue'] = queue[1:] + [queue[0]]
        print queue[0]
        print current_status['queue'][0]
        self.message_queue.append("Repick succeeded. [%s] changed to [%s].\nType _res to get the infomation of the new restaurant." %\
            (self._get_restaurant_info_in_queue(-1), self._get_restaurant_info_in_queue(0)))
        current_status['ordered_user'] = {}
        current_status['repick_user'] = {}
        self._store_queue()

    @botcmd
    def _full_menu(self, mess, args):
        '''Print full menu items'''
        print "_full_menu activated"

        queue = self._get_queue()
        full_menu = json.loads(open("sherpa_menu/%s.json" % queue[0][1]).read())['menu']
        full_menu_string = ""
        for m in full_menu.values():
            full_menu_string += "\n%s %s%s" % (m['name'], m['price'], m['remark'] and ("(%s)" % m['remark']) or "")
            if m.has_key('opts'):
                for o in m['opts']:
                    full_menu_string += "\n  %s" % o['name']
                    for d in o['details']:
                        full_menu_string += "\n   |-%s" % d

        return full_menu_string

    @botcmd
    def _order(self, mess, args):
        '''Order the item in the menu.'''
        print "_order activated"
        #print args

        to_append = True
        ordered_item = ""
        jid = mess.getFrom().getStripped()
        for a in args:
            if a.lower() in ["-r", "r"]:
                print "replace flag set"
                to_append = False
            else:
                ordered_item += u"%s" % a
        if to_append:
            current_status['ordered_user'].setdefault(jid, u"")
            current_status['ordered_user'][jid] = current_status['ordered_user'][jid] + u"\n" + ordered_item
        else:
            current_status['ordered_user'][jid] = ordered_item

        return "%s ordered." % current_status['ordered_user'][jid]

    @botcmd
    def _peek(self, mess, args):
        print "_peek activated"

        if not current_status['ordered_user']:
            return "Nobody ordered so far."

        reply_message = ""
        for user, user_ordered in current_status['ordered_user'].iteritems():
            reply_message += "%s:\n%s\n" % (user, user_ordered)

        return reply_message


    @botcmd(hidden=True)
    def broadcast( self, mess, args):
        """Sends out a broadcast, supply message as arguments (e.g. broadcast hello)"""
        self.message_queue.append( 'broadcast: %s (from %s)' % ( args, mess.getFrom(), ))
        self.log.info( '%s sent out a message to %d users.' % ( mess.getFrom(), len(self.users),))

    def idle_proc( self):

        if not len(self.message_queue):
            return

        # copy the message queue, then empty it
        messages = self.message_queue
        self.message_queue = []

        for message in messages:
            if len(users):
                self.log.info('sending "%s" to %d user(s).' % ( message, len(users), ))
            for user in users:
                self.send(xmpp.JID(user), message)

    def thread_proc( self):
        while not self.thread_killed:
            local_time = time.localtime()
            if 3 == local_time.tm_hour and local_time.tm_min% 15 in [0, 1]:
                self.message_queue.append("It's time for ordering. Type _res to see today's restaurant and menu!")
            for i in range(60 * 2):
                time.sleep(1)
                if self.thread_killed:
                    return

    def _get_main_course(self):
        if not current_status['main_course']:
            json_data = json.loads(open("sherpa_menu/main_course.json").read())
            current_status['main_course'] = json_data
        return current_status['main_course']


    def _get_queue(self):
        if not current_status['queue']:
            json_data = json.loads(open("sherpa_menu/restaurants.json").read())
            current_status['queue'] = json_data['queue']
            current_status['all_res_info'] = json_data['all_res_info']
        return current_status['queue']

    def _get_jsession_id(self):
        if not current_status['jsession_id']:
            content = urllib2.urlopen('''
                http://www.sherpa.com.cn/listRestaurant.shtml?c=SH&a=47002337&t=%E5%8D%8E%E6%97%AD%E5%9B%BD%E9%99%85%E5%B9%BF%E5%9C%BA%20/\
                %20Plaza%20336&t2=null&gs=%E8%A5%BF%E8%97%8F%E4%B8%AD%E8%B7%AF&set_locale=zh_CN
            ''').read()
            try:
                current_status['jsession_id'] = re.search(r'jsessionid=(?P<jsid>\w+)\?', content).group('jsid')
            except:
                current_status['jsession_id'] = ""
        return current_status['jsession_id']

    def _get_restaurant_info_in_queue(self, idx):
        queue = self._get_queue()
        #jsession_id = self._get_jsession_id()
        #return queue[idx][0].replace("JSESSION_ID", jsession_id)
        return queue[idx][0][:queue[idx][0].find("http")]

    def _store_queue(self):
        queue = self._get_queue()
        f = open("sherpa_menu/restaurants.json", 'w')
        f.write(json.dumps({'queue': queue, 'all_res_info': current_status['all_res_info']}))
        f.close()

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print >>sys.stderr, """
        Usage: %s <jid> <password>
        """ % sys.argv[0]

    username, password = sys.argv[1:]
bot = SystemInfoJabberBot(username,password, server="talk.google.com", port=5223)
th = threading.Thread( target = bot.thread_proc)
bot.serve_forever( connect_callback = lambda: th.start())
bot.thread_killed = True
