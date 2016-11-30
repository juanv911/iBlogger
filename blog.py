import os
import re
import random
import hashlib
import hmac
from string import letters
import webapp2
import jinja2
import datetime
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

# Secret key to make HASH more secure
secret = "udacity"



def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

# Create and validate cookies
def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

# Main call to the datastore
class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    # Section for setting and reading cookies
    # Cookies expire when closing browser
    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    # Create user cookie for the current logged in user
    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    # Clear user cookie
    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    # Check to see if user is logged in or not
    # Checks if cookie is the same as the HASH in the datastore
    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

# Section for main page
class MainHandler(BlogHandler):
    def get(self):
        self.render_front()
        
    # Default values
    def render_front(self, title="", content="", username="", error=""):
        # Get current logged in user
        if self.user:
            username = self.user.name

        # Send latest posts to the home page
        posts = db.GqlQuery("SELECT * FROM Post ORDER BY created DESC")
                
        # Format date as 10 Nov 2016
        # Check if Post contains any posts
        if posts:
            for post in posts:
                #comment =  db.GqlQuery("SELECT * FROM Comment WHERE post_id=:1", post.key().id())
                date = str(post.created)
                date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f').strftime("%d %b %Y")
                post_id = post.key().id()

            self.render("index.html", username = username, posts = posts, date = date, post_id = post_id)
        else:
            self.render("index.html", username = username)
        
# Generate random string
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

# Combine random string with SHA256
def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

# Class for user entities
class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    # Create objects before uploading to database
    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(), name = name, pw_hash = pw_hash, email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u
        
# Class for post entities
class Post(db.Model):
    title = db.StringProperty(required = True)
    image = db.StringProperty(required = False)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    username = db.StringProperty(required = True)
    comments = db.IntegerProperty()
    likes = db.IntegerProperty()

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        if self.user:
            return render_str("post.html", p = self, username = self.user.name)
        else:
            return render_str("post.html", p = self)

# Class for comments entities
class Comment(db.Model):
    post_id = db.IntegerProperty(required = True)
    username = db.StringProperty(required = True)
    comment = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)


class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        
        try:
            # Get created date and reformat the datetime format
            date = str(post.created)
            date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f').strftime("%d %b %Y")
        except Exception: 
          pass
        
        if not post:
            self.redirect("/")
            return
        if self.user:
            # Retrieve comments for a specific post
            comments = Comment.all().filter('post_id =', int(post_id))
        # If post_id doesn't exists, redirect to home page
            self.render("post.html", post = post, comments = comments, username = self.user.name,date = date )
        else:
            self.render("post.html", post = post, comments = comments, date = date)

    # Add Comments
    def post(self, post_id):
        # Return data of attributes from entity
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        # Values from input form
        comment = self.request.get('content')
        username = self.user.name
        
        # Check if there is a logged in user and content is provided
        if comment and self.user:
            c = Comment(parent = blog_key(), comment = comment, username = username, post_id = int(post_id))
            c.put()

            # Default value is None
            # If post has not comments, set it to one
            if post.comments == None:
                post.comments = 1
            else:
                post.comments = int(post.comments)+1;

            # Update comments count              
            post.put()
                    
            self.redirect('/post/'+post_id)
        else:
            error = "Content, please!"
            self.render("post.html", title=title, image = image, comments = comments, error=error, username=username)

# Section for creating a new post
class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html", username=self.user.name)
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect("/")

        # Values from input form
        title = self.request.get('title')
        image = self.request.get('image')
        content = self.request.get('content')
        username = self.user.name

        # Check if posts contains title, content and
        # Check if there is a logged in user
        if title and content and self.user:
            p = Post(parent = blog_key(), title = title, image = image, content = content, username = username)
            p.put()
            self.redirect('/post/%s' % str(p.key().id()))
        else:
            error = "Title and content, please!"
            self.render("newpost.html", title=title, image = image, content=content, error=error, username=username)

# Input Validation
USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

# Section for creating new user accounts
class SignUp(BlogHandler):
    def get(self):
        if self.user:
            self.redirect("/",)
        else:
            self.render("signup.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify_pass = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username, email = self.email)

        # Check if inputs are in a valid format
        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify_pass:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError
           
class Register(SignUp):
    def done(self):
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            # If registration is successful, log user in
            self.login(u)
            self.redirect('/')
            
# Section for login
class Login(BlogHandler):
    def get(self):
        if self.user:
            self.redirect('/')
        else:
            self.render('login.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')
        
        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login.html', username = username, error = msg)

# Call logout function to clear user cookie
class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/')


# Show registered users in users page
class ShowUsers(BlogHandler):
    def get(self):
        users = db.GqlQuery("SELECT * FROM User LIMIT 10")
        if self.user:
            self.render('users.html', users = users, username=self.user.name)
        else:
            self.render('users.html', users = users)

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/post/([0-9]+)', PostPage),
    ('/newpost', NewPost),
    ('/signup', Register),
    ('/login', Login),
    ('/logout', Logout),
    ('/users', ShowUsers),
    ], debug=True)

