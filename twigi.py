#!/usr/bin/python
""" Ver 0.02, 2010-03-29
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
* Supports "me too" retweet and old fashioned editable RT
* Enumerates all retweeters of a status (not just "retweeted by 5 people")
* Support for bidi (Arabic, Farsi, Hebrew, etc.)
Dependencies:
* tweepy (http://gitorious.org/tweepy)
* pyfribidi (http://pyfribidi.sourceforge.net/ or apt-get python-pyfribidi)
  [pyfribidi is optional: only if you read bidi languages and your os/browser
  doesn't do bidi by itself]
To do: OAuth, follow/unfollow/block/spam, search, DM
"""

USE_BIDI=True # brown people indicator :)
CACHE_DIR='cache'


from exceptions import Exception
class TwigiError(Exception): pass

### Bidi
def bidi(s): return s # fallback: does nothing
if USE_BIDI:
    try:
        from pyfribidi import log2vis,LTR
        def bidi(s):
            return log2vis(s,base_direction=LTR)
    except ImportError:
        pass
# kamikaze auth mode - mystuff.py should look like:
#     user="..."
#     password="..."
# You'd better chmod mystuff.py to 600
# (w3m runs it itself. Not via a server owned by the httpd unix user)
import mystuff
import tweepy
api=tweepy.API(tweepy.auth.BasicAuthHandler(mystuff.user,mystuff.password),
               cache=tweepy.FileCache(CACHE_DIR))
def menu_ops():
    me=api.me()
    return [('home','?op=home'),
        (me.screen_name,'?op=user'),
        ('@%s' % me.screen_name,'?op=mentions')]
def make_menu_entry(op,query,script_name):
    return '[<a href="%s%s">%s</a>]' % (script_name,query,op)

pat_url = r"((http|https)://([-A-Za-z0-9+&@#/%?=~_()|!:,.;]*[-A-Za-z0-9+&@#/%=~_()|]))"
pat_atuser = r"@([_a-zA-z][_a-zA-z0-9]*)"
def urlize(text,script_name):
    import re
    html=re.sub(pat_url,r'<a target="_blank" href="\1">\1</a>',text)
    html=re.sub(pat_atuser,
        r'@<a target="_blank" href="%s?op=user&name=\1">\1</a>' % script_name,
        html)
    html=html.replace('\n','<br/>\n')
    return html

def reply_url(s,script_name):
    return "%s?op=status&id=%s&status=%%40%s%%20&re_id=%s" % (
        script_name,s.id,s.author.screen_name,s.id)
def rt_url(s,script_name):
    return "%s?op=retweet&id=%s" % (script_name,s.id)
def ert_url(s,script_name):
    from urllib2 import quote
    return "%s?op=status&id=%s&status=RT%%20%%40%s%%20%s&re_id=%s" % (
        script_name,s.id,s.author.screen_name,
        quote(s.text.encode('utf-8')),s.id)
def format_user(u,script_name):
    return '<a href="%(script)s?op=user&name=%(name)s">%(name)s</a>' % {
        'script':script_name, 'name':u.screen_name}
def format_status_link(s,script_name):
    return '[<a href="%s?op=status&id=%s">#</a>]' % (script_name,s.id)
def format_re_link(s,script_name):
    rid=s.in_reply_to_status_id
    if not rid:
        return ''
    return ' <a href="%s?op=status&id=%d"><b>Re:</b> %s</a>' % (script_name,rid,s.in_reply_to_screen_name)
def format_status(s,script_name,full=False):
    from relativeDates import getRelativeTime
    from time import mktime
    res=not full and format_status_link(s,script_name) or ''
    res+='%s %s%s <i>%s</i>' % (
        format_user(s.author,script_name),
        urlize(bidi(s.text),script_name),
        format_re_link(s,script_name),
        getRelativeTime(mktime(s.created_at.utctimetuple())))
    if full:
        rts=s.retweets()
        if rts:
           res+='<p><b>Retweeted by</b>: ' + ', '.join([format_user(r.author,script_name) for r in rts])
        res+='<p>'
        if not api.me().id in [r.author.id for r in rts]:
            res+='[<a href="%s">Retweet</a>]' % rt_url(s,script_name)
        res+='[<a href="%s">Reply</a>][<a href="%s">Editable RT</a>]' % (
            reply_url(s,script_name), ert_url(s,script_name))
        res+='</p>'
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
    menu='\n'.join([make_menu_entry(o[0],o[1],script_name) for o in menu_ops()])
    tl='\n'.join(['<li>%s</li>' % format_status(s,script_name,op=='status') for s in timeline])
    return response_template % {
        'script':script_name,
        'listtag':op=='status' and 'ul' or 'ol',
        'op':op,
        'title':title,
        'menu':menu,
        'feedback':feedback and ('<b>%s</b><br/>' % feedback) or '',
        'status':status.replace('"','&quot;'), # for value="%(status)s"
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
    status_id=form.getvalue('id',None) # for op=='status' and op=='retweet'
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
    if op=='retweet':
        try:
            api.get_status(status_id).retweet()
            print 'Location: %s?op=status&id=%s\n' % (script_name,status_id)
            return
        except Exception,e:
            feedback="Error: %s. Didn't retweet." % e
            op='status'
    elif op=='tweet':
        try:
            api.update_status(status,re_id)
            print 'Location: %s\n' % script_name
            return
        except Exception,e:
            feedback="Error: %s. Didn't tweet." % e
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
        if not feedback:
            feedback="Couldn't fetch timeline :("
            timeline=[]
    # If it's a retweet, show the original instead
    timeline=[s.__dict__.get('retweeted_status') or s for s in timeline]
    response=make_response(script_name=script_name,op=op, timeline=timeline,
        title=title, feedback=feedback, status=status, re_id=re_id)
    print response.encode('utf-8')

if __name__=='__main__':
    try:
        import cgitb; cgitb.enable() # for debugging
        main()
    except tweepy.error.TweepError,e:
       print u"""Content-type: text/html; charset=UTF-8\n
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    <head>
        <title>TwiGI - Error</title>
    </head>
    <body>
        <h3>TwiGI - Error</h3>
        <p>%s</p>
    </body>
</html>""" % e
