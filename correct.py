from flask import Flask, render_template, request, redirect, url_for, g, Response, session
from lxml import etree
from urllib import urlopen, urlencode
import MySQLdb, urllib, json, httplib
from decimal import Decimal
from pprint import pprint
from collections import defaultdict

app = Flask(__name__)
app.debug = True
app.secret_key = open('/home/edward/src/corrections/secret_key').read()[-1]

def group_words(fmt):
    cur = []
    prev = None
    for c in fmt:
        if c.get('wordStart') == 'true' or c.text == ' ':
            if prev:
                yield prev
            prev = list(cur)
            cur = []
        cur.append(c)
    if prev:
        yield prev
    if cur:
        yield cur

def ol_login(username, password):
    host = 'openlibrary.org'
    h1 = httplib.HTTPConnection(host)
    body = json.dumps({'username': username, 'password': password})
    headers = {'Content-Type': 'application/json'}
    h1.request('POST', 'http://' + host + '/account/login', body, headers)
    res = h1.getresponse()
    status = res.status
    h1.close()
    return status == 200

def ia_login(username, password):
    host = 'www.archive.org'
    h1 = httplib.HTTPConnection(host)
    h1.request('GET', 'http://' + host + '/account/login.php')
    res = h1.getresponse()
    res.read()

    assert res.status == 200
    cookies = res.getheader('set-cookie').split(',')
    cookie = ';'.join([c.split(';')[0] for c in cookies])

    body = urlencode({
        'username': username,
        'password': password,
        'submit': 'Log in',
        'referer': '/index.php',
    })
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cookie': cookie,
        'Accept': 'text/html',
    }
    h1.request('POST', 'http://' + host + '/account/login.php', body, headers)
    res = h1.getresponse()
    status = res.status
    body = res.read()
    good_login = 'We will attempt to redirect you now' in body
    
    h1.close()
    return good_login

@app.before_request
def before_request():
    g.db = MySQLdb.connect(db='edward_corrections', user='edward', read_default_file="/home/edward/.my.cnf", use_unicode=True, charset = 'utf8')

@app.after_request
def after_request(r):
    g.db.close()
    return r

def get_leaf0_and_page_count(host, path, identifier):
    url = 'http://%s/~edward/leaf0_and_page_count.php?item_id=%s&doc=%s&path=%s' % (host, identifier, identifier, path)
    reply = json.load(urlopen(url))
    return (reply['leaf0_missing'], reply['page_count'])

class NotFound(Exception):
    pass

def locate(identifier):
    find_file = 'http://www.archive.org/services/find_file.php?loconly=1&file=' + identifier
    root = etree.parse(find_file).getroot()
    if len(root) == 0:
        return NotFound
    return root[0].get('host'), root[0].get('dir') 

@app.route("/add_item", methods=['POST'])
def add_item():
    identifier = request.form['identifier']

    try:
        host, path = locate(identifier)
    except NotFound:
        return redirect(url_for('index'))
    leaf0_missing, page_count = get_leaf0_and_page_count(host, path, identifier)

    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('insert into items (identifier, leaf0_missing, abbyy_page_count) values (%s, %s, %s)', [identifier, leaf0_missing, page_count])

    return redirect(url_for('item', identifier=identifier))

@app.route("/")
def index(error=None):
    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('select identifier, abbyy_page_count from items')
    items = cur.fetchall()
    return render_template('index.html', items=items)

@app.route('/changeset/<changeset_id>')
def view_changeset(changeset_id):
    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('select * from changesets where id=%s', [changeset_id])
    changeset = cur.fetchrow()
    cur.execute('select * from edits where changeset=%s', [changeset_id])
    edits = cur.fetchall()
    return render_template('changeset.html', changeset=changeset, edits=edits)

@app.route("/user/<username>")
def user(username):
    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('select changesets.id, identifier, page, created from changesets, users where user_id=users.id and username=%s order by created', [username])
    changesets = cur.fetchall()
    return render_template('user.html', changesets=changesets)

def get_page_url(identifier, leaf_num):
    host, path = locate(identifier)
    return 'http://%s/fulltext/get_leaf.php?item_id=%s&doc=%s&path=%s&leaf=%d' % (host, identifier, identifier, path, leaf_num)

def get_page(identifier, leaf_num):
    url = get_page_url(identifier, leaf_num)
    return etree.parse(url).getroot()

def get_page_lines(page):
    lines = []
    text_l, text_r = None, None
    for block in page:
        if block.attrib['blockType'] != 'Text':
            continue
        region, text = block
        for par in text:
            if len(par) == 0 or len(par[0]) == 0 or len(par[0][0]) == 0:
                continue
            for line in par:
                char_offset = 0
                for fmt in line:
                    for c in fmt:
                        c.set('char_offset', str(char_offset))
                        char_offset += 1
                l = int(line.get('l'))
                if not text_l or l < text_l:
                    text_l = l
                r = int(line.get('r'))
                if not text_r or r > text_r:
                    text_r = r
                lines.append((int(line.get('t')), int(line.get('b')), line))

    return {'lines': lines, 'text_l': text_l, 'text_r': text_r}

@app.route("/leaf/<identifier>/<int:leaf_num>")
def leaf(identifier, leaf_num):
    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('select edits.* from changesets, edits where changeset=changesets.id and page=%s and identifier=%s', [leaf_num, identifier])
    edits = {}
    for edit in cur.fetchall():
        word_id = 'word_%d_%d' % (edit['line'], edit['char_start'])
        edits[word_id] = edit
    #pprint(edits)

    item = get_item(identifier)
    #print (item['leaf0_missing'], leaf_num)
    page_url = get_page_url(identifier, leaf_num - 1 if item['leaf0_missing'] else leaf_num)
    page = etree.parse(page_url).getroot()
    page_w = int(page.get('width'))
    abbyy = get_page_lines(page)

    text_r = abbyy['text_r']
    text_l = abbyy['text_l']
    text_w = text_r-text_l if (text_r is not None and text_l is not None) else 0
    return render_template('leaf.html', item=item, leaf=leaf_num, lines=abbyy['lines'], \
            page_w=page_w, int=int, Decimal=Decimal, edits=edits, \
            text_x=text_l, text_w=text_w, group_words=group_words, max=max, len=len, page_url=page_url)

def get_item(identifier):
    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('select * from items where identifier=%s', [identifier])
    item = cur.fetchone()
    item['leaf0_missing'] = bool(item['leaf0_missing'])
    return item

@app.route("/item/<identifier>")
def item(identifier):
    item=get_item(identifier)
    return render_template('item.html', item=item, int=int)

def match_edits_to_page(edits, page):
    abbyy = get_page_lines(page)

    to_save = []
    for line_num, (l, b, line) in enumerate(abbyy['lines']):
        if line_num not in edits:
            continue
        chars = []
        for fmt in line:
            for word in group_words(fmt):
                char_offset = int(word[0].get('char_offset'))
                if char_offset not in edits[line_num]:
                    continue
                old_word = ''.join(c.text for c in word)
                new_word = edits[line_num][char_offset]
                #print (line_num, char_offset, ''.join(c.text for c in word), edits[line_num][char_offset])
                to_save.append({
                    'line': line_num,
                    'char_start': char_offset,
                    'old_word': old_word,
                    'new_word': new_word,
                    'l': word[0].get('l'),
                    't': line.get('t'),
                    'r': word[-1].get('r'),
                    'b': line.get('b'),
                })
    return to_save

@app.route("/save/<identifier>/<int:page_num>", methods=['POST'])
def save(identifier, page_num):
    page = get_page(identifier, page_num)
    edits = defaultdict(lambda: defaultdict(unicode))
    for k, replacement in request.form.iteritems():
        if not k.startswith('word_'):
            continue
        line, char = map(int, k.split('_')[1:])
        edits[line][char] = replacement

    to_save = match_edits_to_page(edits, page)
    if not to_save:
        return ''

    cur = g.db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute('insert into changesets (user_id, identifier, page, created) values (%s, %s, %s, now())', [session['user_id'], identifier, page_num])
    changeset_id = g.db.insert_id()

    for edit in to_save:
        keys = ','.join(edit.keys())
        cur.execute('insert into edits (changeset, %s) values (%s)' % (keys, ','.join(['%s'] * (1 + len(edit)))), [changeset_id] + edit.values())
    return ''

ns = '{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}'
page_tag = ns + 'page'

@app.route('/leaders')
def leaders():
    return render_template('leaders.html')

@app.route("/logout")
def logout():
    for f in 'user_id', 'username', 'site':
        if f in session:
            del session[f]
    return redirect(request.referrer or url_for('index'))

@app.route("/do_login", methods=['POST'])
def do_login():
    username = request.form['username']
    password = request.form['password']
    for f in 'user_id', 'username', 'site':
        if f in session:
            del session[f]
    site = None
    if ol_login(username, password):
        site = 'ol'
    elif ia_login(username, password):
        site = 'ia'
    if site:
        session['username'] = username
        session['site'] = site
        cur = g.db.cursor(MySQLdb.cursors.DictCursor)
        cur.execute('select id from users where site=%s and username=%s', [site, username])
        row = cur.fetchone()
        if row:
            session['user_id'] = row['id']
        else:
            cur.execute('insert into users (site, username) values (%s, %s)', [site, username])
            session['user_id'] = g.db.insert_id()
        return 'good'
    return 'bad'

@app.route("/view/<identifier>")
def view(identifier):
    item=get_item(identifier)
    host, path = locate(identifier)
    url = 'http://%s/~edward/read_abbyy.php?item_id=%s&doc=%s&path=%s' % (host, identifier, identifier, path)
    f = urlopen(url)
    page_count = 0
    body = []
    for eve, page in etree.iterparse(f):
        if page.tag != page_tag:
            continue
        for block in page:
            if block.attrib['blockType'] != 'Text':
                continue
            region, text = block
            for par in text:
                cur_par = ''
                if len(par) == 0 or len(par[0]) == 0 or len(par[0][0]) == 0:
                    continue
                for line in par:
                    chars = []
                    for fmt in line:
                        chars += [c.text for c in fmt]
                    cur_par += ''.join(chars)
                body.append(cur_par)
        if page_count == 20:
            break
        page_count += 1

    return render_template('view.html', item=item, int=int, body=body)

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
