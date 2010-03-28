#!/usr/bin/python
""" Ver 0.01, 2010-03-28
Copyleft @TheRealDod, license: http://www.gnu.org/licenses/gpl-3.0.txt
TwiGI (pronounced twi-gee-eye, but Twiggy's also fine because it's lean)
was originally written as a CGI script to be run internally by the w3m text browser
(because even m.twitter.com is too smart for it, and I can't even tweet there).
It could also be cool for stupid mobiles, but it would need OAuth then
(at the moment it simply reads hard-wired user and password from mystuff.py,
so no use running it on a public internet server and let everyone
tweet in your name :) ).
Features:
* Minimum moving parts. assumes browser's really dumb
* Old fashioned retweet:
  * You get to edit the text "RT @theuser blah etc."
  * It appears as "in reply to"
  * No JS character count, but if >140, you get to edit it again
    and the truncated stuff is shown as copy/paste fodder
  * Enumerates all "modern RT" users of a status (not just "retweeted by 5 people")
* Support for bidi (Arabic, Farsi, Hebrew, etc.)
* <200 lines of code [so far]
Dependencies:
* tweepy (http://gitorious.org/tweepy)
* pyfribidi (http://pyfribidi.sourceforge.net/ or apt-get python-pyfribidi)
  [pyfribidi is optional: only if you read bidi languages and your browser+os
  doesn't do bidi by itself]
To do: OAuth, follow/unfollow, search, DM
"""
USE_BIDI=True # brown people indicator :)
import cgitb; cgitb.enable() # for debugging
from urllib2 import quote
from exceptions import Exception
class TwigiError(Exception):
    pass
def bidi(s): return s
if USE_BIDI:
    try:
        from pyfribidi import log2vis,LTR # for rtl languages
        def bidi(s):
            return log2vis(s,base_direction=LTR)
    except ImportError:
        pass
import tweepy
# kamikaze auth mode - mystuff.py should look like:
#     user="..."
#     password="..."
# You'd better chmod it to 600
# (w3m runs it itself. Not via a server owned by the httpd unix user)
import mystuff
api=tweepy.API(tweepy.auth.BasicAuthHandler(mystuff.user,mystuff.password))
import re
menu_ops=['home','mentions']
def make_menu_entry(op,script_name,link=True):
    if link:
        return '[<a href="%s?op=%s">%s</a>]' % (script_name,op,op)
    else:
        return '[%s]' % op
pat_url = r"((http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))"
pat_atuser = r"@([_a-zA-z][_a-zA-z0-9]*)"
def urlize(text,script_name):
    html=re.sub(pat_url,r'<a target="_blank" href="\1">\1</a>',text)
    html=re.sub(pat_atuser,
        r'@<a target="_blank" href="%s?op=user&name=\1">\1</a>' % script_name,
        html)
    html=html.replace('\n','<br/>\n')
    return html
def dequote(s):
    return s.replace('"','&quot;')
def reply_url(s,script_name):
    return "%s?op=home&status=%%40%s%%20&re_id=%s" % (
        script_name,s.author.screen_name,s.id)
def rt_url(s,script_name):
    return "%s?op=home&status=RT%%20%%40%s%%20%s&re_id=%s" % (
        script_name,s.author.screen_name,quote(s.text.encode('utf-8')),s.id)
def format_user(u,script_name):
    return '<a href="%(script)s?op=user&name=%(name)s">%(name)s</a>' % {
        'script':script_name, 'name':u.screen_name}
def format_status_link(s,script_name):
    return '[<a href="%s?op=status&id=%s">#</a>]' % (script_name,s.id)
def format_re_link(s,script_name):
    rid=s.in_reply_to_status_id
    if not rid:
        return ''
    return ' <a href="%s?op=status&id=%d">Re: %s</a>' % (script_name,rid,s.in_reply_to_screen_name)
def format_status(s,script_name,full=False):
    res='[<a href="%s">R</a>][<a href="%s">RT</a>]%s %s%s' % (
        reply_url(s,script_name),
        rt_url(s,script_name),
        format_user(s.author,script_name),
        urlize(bidi(s.text),script_name),
        format_re_link(s,script_name))
    if full:
        rts=s.retweets()
        if rts:
           res+='<br/>RTs: ' + ', '.join([format_user(r.author,script_name) for r in rts])
    else:
        res+=format_status_link(s,script_name)
    return res

response_template=u"""Content-type: text/html; charset=UTF-8\n
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    <head>
        <title>TwiGI - %(title)s</title>
    </head>
    <body>
        <h3>TwiGI - %(title)s</h3>
        %(menu)s<br/>
        <form action="%(script)s">
            <input type="hidden" name="op" value="tweet">
            <input type="hidden" name="re_id" value="%(re_id)s">
            <input name="status" size="60" maxlength="140" value="%(status)s">
            <input type="submit" value="Tweet">
        </form>
        %(feedback)s
        <%(listtag)s>
%(timeline)s
        </%(listtag)s>
    </body>
</html>"""
def make_response(script_name='',op='home', title='home', timeline=[],
                    feedback='', status='', re_id=''):
    menu='\n'.join([make_menu_entry(o,script_name,status or o!=op) for o in menu_ops])
    tl='\n'.join(['<li>%s</li>' % format_status(s,script_name,op=='status') for s in timeline])
    return response_template % {
        'script':script_name,
        'listtag':op=='status' and 'ul' or 'ol',
        'op':op,
        'title':title,
        'menu':menu,
        'feedback':feedback and ('<b>%s</b><br/>' % feedback) or '',
        'status':dequote(status),
        're_id':re_id,
        'timeline':tl}
def main():
    import os,cgi
    try:
        script_name=os.environ['SCRIPT_NAME']
    except:
        raise TwigiError,"Program should run as a cgi"
    form = cgi.FieldStorage()
    feedback=''
    op=form.getvalue('op','home')
    name=form.getvalue('name',api.me().screen_name) # for op=='user'
    status_id=form.getvalue('id',None) # for op=='status'
    status=unicode(form.getvalue('status',''),'utf-8')
    re_id=form.getvalue('re_id','').strip() or None
    if len(status)>140:
        feedback='truncated "%s"' % status[140:]
        status=status[:140]
        if op=='tweet':
            feedback+=' (tweet not sent)'
            op='home'
    if op=='tweet' and not status:
        feedack="Didn't send an empty tweet"
        op='home'
    if op=='tweet':
        try:
            api.update_status(status,re_id)
            status=''
            re_id=''
            print 'Location: %s\n' % script_name
            return
        except:
            feedback="Network error. Didn't tweet."
            op='home'
    tlhandler=None # handler to get timeline
    title=op
    if op=='mentions':
        tlhandler=api.mentions
        title='@'+api.me().screen_name
    elif op=='user':
        tlhandler=lambda: api.user_timeline(name)
        title=name
    elif op=='status':
        tlhandler=lambda: [api.get_status(status_id)]
    else: # gracefully deciding it's "home"
        op='home'
        tlhandler=api.home_timeline
    try:
        timeline=tlhandler()
    except:
        raise Exception,status_id
        if not feedback:
            feedback="Couldn't fetch timeline :("
            timeline=[]
    response=make_response(script_name=script_name,op=op, timeline=timeline,
        title=title, feedback=feedback, status=status, re_id=re_id)
    print response.encode('utf-8')

if __name__=='__main__':
    main()
