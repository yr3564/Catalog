import random
import string
import httplib2
import json
import requests
from flask import Flask, render_template, request, \
redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc  # nopep8
from sqlalchemy.orm import sessionmaker  # nopep8
from catalog import Base, Categories, SportItem, User  # nopep8
from flask import session as login_session  # nopep8
from oauth2client.client import flow_from_clientsecrets  # nopep8
from oauth2client.client import FlowExchangeError  # nopep8
from flask import make_response  # nopep8


app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Catalog Item APP"


# Connect to Database and create database session
engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

# Create anti-forgery state token


@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps /
                                 ('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # See if a user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px; \
    border-radius: 150px; -webkit-border-radius: \
    150px; -moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
        # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/')
@app.route('/publiccatalog/')
def showCatalog():
    sports = session.query(Categories).order_by(asc(Categories.name))
    latest_items = session.query(SportItem).order_by(asc(SportItem.id)) \
    .limit(10)
    return render_template \
    ('sportcategories.html', sports=sports, latest_items=latest_items)


@app.route('/publiccatalog/<int:category_id>/items/')
def selectCategory(category_id):
    if 'username' not in login_session:
        return redirect('/login')
    sports1 = session.query(Categories).order_by(asc(Categories.name))
    sports = session.query(Categories).filter_by(id=category_id).one()
    sport_items = session.query \
    (SportItem).filter_by(sportCategories_id=category_id).all()
    return render_template('categoryItemList.html', \
                           sports=sports, sport_items=sport_items, \
                           sports1=sports1)


@app.route('/publiccatalog/<int:sportItem_id>/item/description')
def itemDescription(sportItem_id):
    item_descriptions = session.query(SportItem) \
    .filter_by(id=sportItem_id).one()
    return render_template('itemDescription.html', \
                           item_descriptions=item_descriptions)


@app.route('/privatecatalog/', methods=['GET', 'POST'])
def addItem():
    if 'username' not in login_session:
       return redirect('/login')
    if request.method == 'POST':
        addedItem = SportItem(name=request.form['name'], \
                                  description=request.form['description'],
                                  sportCategories_id=request.form['Sport'])
        session.add(addedItem)
        session.commit()
        return redirect(url_for('showCatalog'))
    else:
        return render_template('addItem.html')


@app.route('/privatecatalog/<int:sportItem_id>/item/edit', \
           methods=['GET', 'POST'])
def editItem(sportItem_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(SportItem).filter_by(id=sportItem_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['Sport']:
            editedItem.price = request.form['Sport']
        session.add(editedItem)
        session.commit()
        return redirect(url_for('showCatalog'))
    else:
        return render_template('editItemCatalog.html', \
                               sportItem_id=sportItem_id)


@app.route('/privatecatalog/<int:sportItem_id>/item/delete', \
           methods={'GET', 'POST'})
def deletedItem(sportItem_id):
        if 'username' not in login_session:
            return redirect('/login')
        deleteItem = session.query(SportItem).filter_by(id=sportItem_id).one()
        if request.method == 'POST':
            session.delete(deleteItem)
            session.commit()
            return redirect(url_for('showCatalog'))
        else:
            return render_template \
            ('deleteItemName.html', \
             sportItem_id=sportItem_id, deleteItem=deleteItem)


# "This shows specific category and Items"


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
