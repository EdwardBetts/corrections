from flask import Flask, render_template, request, redirect, url_for, g, Response
from lxml import etree
from urllib import urlopen
import MySQLdb, urllib, json
from decimal import Decimal
from pprint import pprint

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

@app.route("/leaf/<identifier>/<int:leaf>")
def leaf(identifier, leaf):
    item = get_item(identifier)
    host, path = locate(identifier)
    url = 'http://%s/~edward/get_leaf.php?item_id=%s&doc=%s&path=%s&leaf=%d' % (host, identifier, identifier, path, leaf)
    print url
    page = etree.parse(url).getroot()
    page_w = int(page.get('width'))
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

    text_w = text_r-text_l if (text_r is not None and text_l is not None) else 0
    return render_template('leaf.html', item=item, leaf=leaf, lines=lines, \
            page_w=page_w, int=int, Decimal=Decimal, \
            text_x=text_l, text_w=text_w, group_words=group_words, max=max, len=len)

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

@app.route("/login")
def login():
    return render_template('login.html')

@app.route("/save/<identifier>/<int:page>", methods=['POST'])
def save(identifier, page):
    edits = []
    for k, v in request.form.iteritems():
        if not k.startswith('word_'):
            continue
        line, char = map(int, k.split('_')[1:])
        edits.append((identifier, page, line, char, v))
    for e in sorted(edits):
        print e
    return ''

ns = '{http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml}'
page_tag = ns + 'page'

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
