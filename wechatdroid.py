#!/usr/bin/env python
#coding: utf-8

'''a wechat droid'''

__author__ = 'Yifei Kong'
__email__ = 'kongyifei@gmail.com'
__date__ = '2012-09-15'
__license__ = 'MIT'
__version__ = '0.1'

import requests, hashlib, re, json, sqlite3, random, sys

class WechatDroid:

    def __init__(self, uin, passwd):
        #QQ的帐号和密码
        self.uin = uin
        self.passwd = passwd
        #消息池
        self.msgPool = [] #只保存msgid len(msgPool) == 5*msgRate
        self.msgNew = [] #新消息数 + 5
        self.msgRate = 5 #上次消息数
        #模拟浏览器
        self.cookies = {}
        self.headers = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:15.0) Gecko/20100101 Firefox/15.0'}
        #以下两个URL参数变化较少
        self.loginURI = r'http://ptlogin2.qq.com/login?ptlang=2052&aid=522017401&u1=http%3A%2F%2Fmp.weixin.qq.com%2Fcgi-bin%2Findexpage%3Ft%3Dwxm-index%26lang%3Dzh_CN%26ss%3D%26validcnt%3D%26clientaddr%3D2334234124&mibao_css=m_ptmail&from_ui=1&ptredirect=1&h=1&wording=%E5%BF%AB%E9%80%9F%E7%99%BB%E5%BD%95&u={0}&p={1}&verifycode={2}&fp=loginerroralert&action=11-10-41347&g=1&t=1&dummy='
        self.checkinURI = r'http://check.ptlogin2.qq.com/check?uin={0}&appid=522017401&ptlang=2052'
        #这两个URL参数较多
        self.getMsgURI = r'http://mp.weixin.qq.com/cgi-bin/getmessage'
        self.getMsgNumURI = r'http://mp.weixin.qq.com/cgi-bin/getnewmsgnum'
        self.sendMsgURI = r'http://mp.weixin.qq.com/cgi-bin/singlesend'
        #用于获取新消息
        self.lastMsgId = ''
        
        self.db = './wechatdroid.db'

    def _httpPost(self, uri, data=None, params=None):
        '''post method dealing with cookies'''
        try:
            r = requests.post(uri, data=data, params=params, cookies=self.cookies, headers=self.headers)
            self.cookies = r.cookies
            return r.json or r.text
        except :
            print 'we lost something'

    def _httpGet(self, uri, params=None):
        '''get method dealing with cookies'''
        try:
            r = requests.get(uri, params=params, cookies=self.cookies, headers=self.headers)
            self.cookies = r.cookies
            return r.json or r.text
        except :
            print 'we lost something'

    def _getHash(self, code1, code2):
        '''
        a little black magic tencnet uses to protect your password
        see more at http://www.oschina.net/code/snippet_219811_13204
        '''
        
        print 'calculating...'
        hex_md5hash = lambda sth:hashlib.md5(sth).hexdigest().upper()
        hexchar2bin = lambda sth:''.join([chr(int(i, 16)) for i in sth.split(r'\x')[1:]])

        passwdPreHash = hex_md5hash(hashlib.md5(self.passwd).digest() + hexchar2bin(code2))
        return hex_md5hash(passwdPreHash + code1.upper()) 

    def _checkin(self):
        '''
        询问服务器是否需要验证码
        '''
        
        print 'getting verify code'
        r = self._httpGet(self.checkinURI.format(self.uin))
        if r is not None:
            matchResult = re.match(r"\w+\('(\d)','(.*)','(.*)'\);", r)
            if matchResult.group(1) != 0:
                return matchResult.group(2), matchResult.group(3)
            else:
                print 'verify code needed!\ntry login on this IP address 4 or 5 times to avoid this.'
                sys.exit(-1)# ugly, i know it

    def login(self):
        '''登录'''
        print 'logging in...'
        verifyCode1, verifyCode2 = self._checkin()
        r = self._httpGet(self.loginURI.format(self.uin, self._getHash(verifyCode1, verifyCode2), verifyCode1))
        if u'登录成功' in r: 
            print 'logged in'

    def _getMsgNum(self):
        '''获得新消息数'''

        params = {'t': 'ajax-getmsgnum', 'lastmsgid': self.lastMsgId}
        data = {'ajax': 'true'}
        r = self._httpPost(self.getMsgNumURI, params=params, data=data)
        #print '%s new messages'% r.json['newTotalMsgCount']
        try:
            return int(r['newTotalMsgCount'])
        except:
            return 0

    def _processMsg(self, msg):
        '''处理消息'''
        
        msg['content'] = self._prettifyContent(msg['content'])
        print msg['content']
        if msg['content'].startswith('teach'):
            self._learn(msg)
        else:
            self._respondMsg(msg)

    def _learn(self, msg):
        '''学习新会话内容'''

        print 'learning...'
        question, answer = msg['content'][5:].split('=')
        question = self._prettifyContent(question).lower()
        answer = self._prettifyContent(answer)
        with sqlite3.connect(self.db, isolation_level=None) as db:
            c = db.cursor()
            c.execute("insert into known (question, answer) values(?,?)", (question, answer))
            c.execute("delete from unknown where question = ?", (question,))
        self._sendMsg(fakeId=msg['fakeId'], content=u'学会了')

    def _respondMsg(self, msg):
        '''回应消息'''

        print 'responding...'
        question = self._prettifyContent(msg['content']).lower()
        with sqlite3.connect(self.db, isolation_level=None) as db:
            c = db.cursor()
            answers = c.execute("select answer from known where question = ?", (question,)).fetchall()
            print answers
            if answers == []:
                c.execute("insert into unknown (question) values (?)", (question,))
                self._sendMsg(fakeId=msg['fakeId'], content=u'这是什么?')
                self._sendMsg(fakeId=msg['fakeId'], content=u'可以使用\n"teach 问题=答案"\n来教我哦。')
            else:
                #[(answer1,), (answer2,)]
                #print random.sample(answers,1)[0][0]
                self._sendMsg(fakeId=msg['fakeId'], content=random.sample(answers,1)[0][0])

    def _prettifyContent(self,s):
        return s.replace('&nbsp;', ' ').rstrip(u'.?!。？！ ').lstrip()

    def _sendMsg(self, fakeId, content):
        '''发送消息'''

        params = {
            't': 'ajax-response',
            'lang': 'en'
        }
        data = {
            'type': '1',
            'content': content,
            'error': 'false',
            'tofakeid': fakeId,
            'ajax': 'true',
            'fid':''
        }
        self._httpPost(self.sendMsgURI, params=params, data=data)

    def _getMsg(self, init=False, count='50'):
        '''收取消息'''

        params={
            't': 'wxm-message',
            'lang': 'zh_CN',
            'count': count, 
            'timeline':'1', 
            'day': '0' #'0' means today
        }
        r = self._httpGet(self.getMsgURI, params=params)
        if r is not None:
            print 'getting last msg id...'
            self.lastMsgId = re.findall(r"DATA.lastMsgId = '(\d+)';", r)[0]
            print 'getting msgList...'
            msgsString = re.findall(r"DATA\.List\.msgList\s=\s(.*);DATA\.lastMsgId", r.replace('\n', '').replace("'", '"').replace(r'\x', ''))[0]
            msgs = json.loads(msgsString)

            if init == True:
                self.msgPool.extend([msg['id'] for msg in msgs])
                print '%s initial messages got!' %len(self.msgPool)
            else:
                print 'getting messages...'
                self.msgNew.extend(msgs)

    def work(self):
        '''
        工作循环,初始化后阻塞在收取消息
        处理self.msgNew池中的新消息后加入self.msgPool队列
        '''

        #初始化
        print 'work started'
        while self.lastMsgId == '':
            self._getMsg(init=True)
        self.msgPool.append(-1) #in case no initial messages got, negative one is smaller than any str
        self.msgPool.sort()
        #print 'now,we have %s messages in pool' %len(self.msgPool)
        
        #工作循环
        while 1:
            newMsgNum = self._getMsgNum()
            if newMsgNum > 0:
                self._getMsg(count=newMsgNum+5)
            while self.msgNew:
                print '%s in pool, %s to be processsed' %(len(self.msgPool), len(self.msgNew))
                msg = self.msgNew.pop()
                if msg['id'] > self.msgPool[-1]: #str compare here
                    self._processMsg(msg)
                    self.msgPool.append(msg['id'])

            self.msgPool = self.msgPool[-self.msgRate * 5:]#删除旧消息，保证已处理消息队列不太大
            self.msgPool.sort()
            self.msgRate = newMsgNum

if __name__ == '__main__':
    r2d2 = WechatDroid('qqnumber', 'qqpassword')
    r2d2.login()
    r2d2.work()
