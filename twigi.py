#!/usr/bin/python
""" Ver 0.06, 2010-04-15
Copyleft @TheRealDod, license: http://www.gnu.org/licenses/gpl-3.0.txt
TwiGI (pronounced twi-gee-eye, but Twiggy's also fine because it's lean)
is a minimalistic twitter web GUI for dumb phones and browsers without 
JS and/or bidi support.

To do: show bio, follow/unfollow/block/spam, search (and #hash links), DM

Dependencies:
* tweepy (http://gitorious.org/tweepy)
* pyfribidi (http://pyfribidi.sourceforge.net/ or apt-get python-pyfribidi)
  [pyfribidi is optional: only if you read bidi languages and client's
  phone/browser doesn't do bidi by itself]
"""
### for debugging
import cgitb; cgitb.enable()

import logging
logging.basicConfig(level=logging.ERROR, filename='twigi.log',filemode='a')

### See myoauth_example.py ###
from myoauth import consumer_key, consumer_secret

### begin setup
DEFAULT_BIDI=False # most modern phones do their own bidi
IDLE_TIMEOUT_SECONDS=60*60
CACHE_DIR='cache'
### end setup

from exceptions import Exception
class TwigiError(Exception): pass

import os,re,cgi,Cookie,tweepy
import relativeDates,time

### timestamp for integrity checks
def maketimestamp():
    return int(time.mktime(time.gmtime()))

### bidi
try:
    from pyfribidi import log2vis,LTR
    def bidi(s,enabled=DEFAULT_BIDI):
        if not enabled: return s
        return log2vis(s,base_direction=LTR)
    FRIBIDI_SUPPORTED=True
except ImportError: # can't import pyfribidi, never mind
    def bidi(s,enabled=DEFAULT_BIDI): return s
    FRIBIDI_SUPPORTED=False # don't show r2l/l2r menu items

### patterns for urlize
PAT_URL = r"((http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))"
PAT_ATUSER = r"@([_a-zA-z][_a-zA-z0-9]*)"

REDIRECT_TEMPLATE=u"""%(headers)s\n
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    <head>
        <title>TwiGI - redirecting...</title>
        <meta http-equiv="refresh" content="0; url=%(redirect)s"/>
    </head>
    <body>
    Redirecting...
    </body>
</html>"""
RESPONSE_TEMPLATE=u"""%(headers)s\n
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    <head>
        <title>TwiGI - %(title)s</title>
    </head>
    <body>
        <h3>TwiGI - %(title)s</h3>
        <div id="content">%(content)s</div>
    </body>
</html>"""
def make_response(title='(untitled)',content='???',
        headers='Content-Type: text/html'):
    return RESPONSE_TEMPLATE % {
        'title':title,'content':content,'headers':headers}

CONTENT_TEMPLATE=u"""%(menu)s<br/>
<form action="%(script)s">
    <input type="hidden" name="op" value="tweet">
    <input type="hidden" name="re_id" value="%(re_id)s">
    <input name="status" maxlength="140" value="%(status)s">
    <input type="submit" value="Tweet">
</form>
%(feedback)s
<%(listtag)s>
%(timeline)s
</%(listtag)s>
<i>Bugs? Question? tell @<a href="%(script)s?status=@TheRealDod%%20re%%20%%23TWiGI%%20">TheRealDod</a></i><br/>
"""

LOGIN_TEMPLATE="""<h3>Please <a href="%(login_url)s">login via Twitter</a></h3>
Mobile friendly url: <b>j.mp/mytwit</b><br/>
TwiGI - (pronounced twi-gee-eye) is a minimalistic Twitter interface for lame phones and browsers without Javascript.<br/>
As skinny as a skeleton, as old-fashioned as a dodo, but it can tweet from
<a target="_blank" href="http://twitpic.com/1cskf1">my</a> phone :)<br/>
New features will be added whenever procrastination is called for :)<br/>
Code is available <a target="_blank" href="http://bit.ly/twigigist">here</a>.<br/>
Enjoy, @<a target="_blank" href="http://twitter.com/TheRealDod">TheRealDod</a>.
"""

### The TwiGI class
class TwiGI():
    def __init__(self):
        try:
            self.script_name=os.environ['SCRIPT_NAME']
        except:
            raise TwigiError,"Program should run as a cgi"
        self.username=None
        self.login_url=None # If not None, output() will produce login page
        self.login_title='Welcome' # Might change to 'Auto logged out' etc.
        self.redirect_url=None
        self.form = cgi.FieldStorage()
        self.cookie = Cookie.SimpleCookie()
        if os.environ.has_key('HTTP_COOKIE'):
            self.cookie.load(os.environ['HTTP_COOKIE'])
        # Integrity checks
        cookie_problem=None
        # Check if expired
        try:
            ts=int(self.cookie['timestamp'].value)
        except: # no timestamp cookie
            ts=None
        if ts and maketimestamp()-ts>IDLE_TIMEOUT_SECONDS:
            cookie_problem='Auto logged out because of idle time'
        else: # check for forged cookie
            hash=self.cookie.has_key('hash') and self.cookie['hash'].value or ''
            if hash!=self.cookiehash():
                cookie_problem="Corrupt cookies, or you're trying to hack this :)"
        if cookie_problem:
            self.login_title=cookie_problem
        # Find out where we are OAuth-wise
        self.auth=tweepy.OAuthHandler(consumer_key, consumer_secret)
        if not cookie_problem and self.cookie.has_key('access_key') and self.cookie.has_key('access_secret'):
            # already OAuthed
            self.auth.set_access_token(self.cookie['access_key'].value, self.cookie['access_secret'].value)
        elif (not cookie_problem and
              self.cookie.has_key('request_key') and
              self.cookie.has_key('request_secret') and
              'oauth_token' in self.form.keys()):
            # back from twitter OAuth redirection
            self.redirect_url=self.script_name # make sure cookies are stored, in case of script error or old IIS server :)
            self.auth.set_request_token(self.cookie['request_key'].value, self.cookie['request_secret'].value)
            self.auth.get_access_token(verifier=self.form.getvalue('oauth_token')) # might throw error(?!?)
            for c in ['request_key','request_secret']:
                if self.cookie.has_key(c): self.cookie[c]['max-age']=0
            self.cookie['access_key']=self.auth.access_token.key
            self.cookie['access_secret']=self.auth.access_token.secret
        else: # need to login
            for c in ['access_key','access_secret']:
                if self.cookie.has_key(c):
                    self.cookie[c]='' # we don't want it in the hash :)
                    self.cookie[c]['max-age']=0
            self.login_url=self.auth.get_authorization_url() # this will make output() show a login page
            self.cookie['request_key']=self.auth.request_token.key
            self.cookie['request_secret']=self.auth.request_token.secret
        # take care of bidi
        if self.form.has_key('bidi'):
            self.cookie['bidi']=self.form.getvalue('bidi')
        if self.cookie.has_key('bidi'):
            self.use_bidi=self.cookie['bidi'].value.lower()=='on'
        else:
            self.use_bidi=DEFAULT_BIDI
    def cookiehash(self):
        'generate hash of timestamp and "perishable cookies"'
        from hashlib import sha1
        not_empty=False
        hash=sha1(consumer_secret) # something a forger wouldn't know
        for key in ['access_key','access_secret','timestamp']:
            if self.cookie.has_key(key) and self.cookie[key].value:
                hash.update(self.cookie[key].value)
                not_empty=True
        if not_empty:
            hash.update(consumer_key) # for good measure :)
            return hash.digest().encode('base64').strip()
        # The "fresh out of cookies" case :)
        return ''
    def make_headers(self):
        res="Content-Type: text/html; charset=utf-8"
        self.cookie['timestamp']=maketimestamp()
        self.cookie['hash']=self.cookiehash()
        c=self.cookie.output()
        if c: res+='\n'+c
        return res

    def urlize(self,text):
        def link_handler(m):
            from urllib2 import quote
            return '<a target="_blank" href="http://google.com/gwt/n?u=%s">%s</a>' % (
                quote(m.group(1)),m.group(1))
        html=re.sub(PAT_URL,link_handler,text)
        html=re.sub(PAT_ATUSER,
            r'@<a href="%s?op=user&name=\1">\1</a>' % self.script_name,
            html)
        html=html.replace('\n','<br/>\n')
        return html

    def reply_url(self,s):
        return "%s?op=status&id=%s&status=%%40%s%%20&re_id=%s" % (
            self.script_name,s.id,s.author.screen_name,s.id)
    def rt_url(self,s):
        return "%s?op=retweet&id=%s" % (self.script_name,s.id)
    def ert_url(self,s):
        from urllib2 import quote
        return "%s?op=status&id=%s&status=RT%%20%%40%s%%20%s&re_id=%s" % (
            self.script_name,s.id,s.author.screen_name,
            quote(s.text.encode('utf-8')),s.id)
    def format_user(self,u):
        return '<a href="%(script)s?op=user&name=%(name)s">%(name)s</a>' % {
            'script':self.script_name, 'name':u.screen_name}
    def format_re_link(self,s):
        rid=s.in_reply_to_status_id
        if not rid: return ''
        return '<a href="%s?op=status&id=%d"><b>Re:</b> %s</a>' % (
            self.script_name,rid,s.in_reply_to_screen_name)
    def format_status_link(self,s):
        return '[<a href="%s?op=status&id=%s">&bull;</a>]' % (
            self.script_name,s.id)
    def format_status(self,s,single=False):
        res=not single and self.format_status_link(s) or ''
        res+='%s %s %s <span dir="ltr"><i>%s</i></span>' % (
            self.format_user(s.author),
            self.urlize(bidi(s.text,enabled=self.use_bidi)),
            self.format_re_link(s),
             relativeDates.getRelativeTime(time.mktime(s.created_at.utctimetuple())))
        if single:
            rts=s.retweets()
            if rts:
               res+='<p><b>Retweeted by</b>: '+', '.join([self.format_user(r.author) for r in rts])+'</p>'
               res+='</p>'
            res+='<p>'
            if not self.username.lower() in [r.author.screen_name.lower() for r in rts]:
                res+='[<a href="%s">Retweet</a>]' % self.rt_url(s)
            res+='[<a href="%s">Reply</a>][<a href="%s">Editable RT</a>]' % (
                self.reply_url(s), self.ert_url(s))
            res+='</p>'
        return res

    def menu_ops(self):
        if self.username:
            res=[('home','?op=home'),
                (self.username,'?op=user'),
                ('@%s' % self.username,'?op=mentions')]
            if FRIBIDI_SUPPORTED:
                res.append(self.use_bidi and (
                    'l2r','?bidi=off') or (
                    'r2l','?bidi=on'))
            res.append(('logout','?op=logout'))
            return res
        else: # just in case we're not *at* the login page(?!?)
            return [('To welcome page','?op=logout')]
    def make_menu_entry(self,op,query):
        return '[<a href="%s%s">%s</a>]' % (self.script_name,query,op)

    def output(self):
        self.op=self.form.getvalue('op','home')
        if self.op=='logout':
            for c in ['request_key','request_secret','access_key','access_secret','timestamp','hash']:
                if self.cookie.has_key(c):
                    self.cookie[c]='' # so that they don't enter the cookie hash and then expire
                    self.cookie[c]['max-age']=0
            self.redirect_url=self.script_name+'?op=home'
        if self.redirect_url: # Do a lame meta refresh redirect, because these are easier to debug
            return REDIRECT_TEMPLATE % {'headers':self.make_headers(), 'redirect':self.redirect_url}
        if self.login_url:
           return make_response(
               headers=self.make_headers(),
               title=self.login_title,
               content=LOGIN_TEMPLATE % {'login_url':self.login_url})
        # create the api (auth should be fine if we got this far)
        self.username=self.auth.get_username()
        self.api=tweepy.API(self.auth,cache=tweepy.FileCache(CACHE_DIR))
        # feedback: for error messages and notifications
        self.feedback=''
        # name: for op=='user'
        self.name=self.form.getvalue('name',self.username)
        # status_id: for op=='status' and op=='retweet'
        self.status_id=self.form.getvalue('id',None)
        # status: information to put inside the for field
        # (except if op=='tweet', where this is what we tweet)
        self.status=unicode(self.form.getvalue('status',''),'utf-8')
        self.re_id=self.form.getvalue('re_id','').strip() or None
        if len(self.status)>140:
            self.feedback='truncated "%s"' % self.status[140:]
            self.status=self.status[:140]
            if self.op=='tweet':
                self.feedback+=' (tweet not sent)'
                self.op='home'
        if self.op=='tweet' and not self.status:
            self.feedack="Didn't send an empty tweet"
            self.op='home'
        if self.op=='retweet':
            try:
                self.api.get_status(self.status_id).retweet()
                self.feedback="Retweeted."
            except Exception,e:
                self.feedback="Error: %s. Didn't retweet." % e
            self.op='status'
        elif self.op=='tweet':
            try:
                self.api.update_status(self.status,self.re_id)
                self.feedback="Tweeted."
                self.status=""
                self.re_id=""
            except Exception,e:
                self.feedback="Error: %s. Didn't tweet." % e
            self.op='home'
        tlhandler=None # handler to get timeline
        title=self.op
        if self.op=='mentions':
            tlhandler=self.api.mentions
            title='@'+self.username
        elif self.op=='user':
            tlhandler=lambda: self.api.user_timeline(self.name)
            title=self.name
        elif self.op=='status':
            tlhandler=lambda: [self.api.get_status(self.status_id)]
        else: # gracefully deciding it's "home"
            self.op='home'
            tlhandler=self.api.home_timeline
        try:
            timeline=tlhandler()
        except Exception,e:
            self.feedback=str(e)
            timeline=[]
        # If it's a retweet, show the original instead
        timeline=[s.__dict__.get('retweeted_status') or s for s in timeline]
        menu='\n'.join(
            [self.make_menu_entry(o[0],o[1]) for o in self.menu_ops()])
        tl='\n'.join(
            ['<li>%s</li>' % self.format_status(s,single=self.op=='status')
                for s in timeline])
        response_content=CONTENT_TEMPLATE % {
            'script':self.script_name,
            'op':self.op,
            'menu':menu,
            'status':self.status.replace('"','&quot;'),
            'timeline':tl,
            'listtag':self.op=='status' and 'ul' or 'ol',
            'feedback':self.feedback and ('<b>%s</b><br/>' % self.feedback) or '',
            're_id':self.re_id}
        response=make_response(headers=self.make_headers(),
            title=title, content=response_content)
        return response.encode('utf-8')

if __name__=='__main__':
    try:
        print TwiGI().output()
    except (tweepy.error.TweepError,TwigiError),e:
        print make_response(title="Error", content=e)
