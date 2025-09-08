# BONASO Data Portal Server: Setup
*Please also review guides to setting up the web frontend and the mobile app.*

## 1. Requirements:
In order to setup the server, the following tools are required:
- [Python](https://www.python.org/downloads/) (~v. 3.13) (make sure this is added to path)
- Pip (~v 25.1.1)
- [PostgreSQL](https://www.postgresql.org/download/) (~v 17.5)
- All other dependencies are pinned in `requirements.txt` (Django, DRF, psycopg, PyJWT, etc.)

On first setup, make sure you run:
```bash
python -m venv venv
source venv/bin/activate   # On Mac/Linux
venv\Scripts\activate      # On Windows
pip install -r requirements.txt
```

There are better guides online for setting up Django on your PC (it's a bit old, but I like this one from [w3](https://www.w3schools.com/django/django_intro.php), particularly "Django Intro" through "Install Django"). *Make sure you set up a virtual environment and use that whenever running commands*. 

---

## 2. Environment Variables:
The .env file holds the following variables:
- Database URL (connection to the PostgreSQL database)
- Secret key (for Django auth magic)
- Debug variable (is this production grade or local dev)

Make sure that you set these variables. 

**Example**:

```bash
DATABASE_URL=postgres://user:password@localhost:5432/bonaso
SECRET_KEY=super_secret_key_here
DEBUG=True
```

You can read more about the secret key [here](https://docs.djangoproject.com/en/5.2/ref/settings/#std-setting-SECRET_KEY) at the Django docs. 

The database URL should point to whatever database is being used (either your local DB or whatever DB is installed on the server). It should use the "postgres://username:password@host:port/name" format. 

**ONLY SET DEBUG TO TRUE IN LOCAL ENIRONMENTS!** Setting it as true disables certain security features, which is generally bad (and may crash the site since we rely on HTTP cookies).

---

## 3. Migrate Database:

Whenever you first load this project on a new device/server, run:

```bash
python manage.py migrate 
```

If you make any changes to any of the model files, make sure you run:
```bash
python manage.py makemigrations
```
before running "migrate."

---

## 4. Create a Superuser:
Pretty much every endpoint here is protected, so you'll need to create a superuser to do anything. Start by running:

```bash
python manage.py createsuperuser
```

This actually won't be enough to access the entire site, however. You'll also need to run:

```python
import User from users.models
import Organizations from organizations.models
org = Organization.objects.create(name='BONASO')

user = User.objects.get(username=[your_username])
user.role = 'admin'
user.organization=(org)
user.save()
```

This will ensure that your user has a role and an organization (both of which are required to actually do anything on the site with our custom auth logic), since our custom [RoleRestrictedViewset](/users/restrictviewset.py) will not allow any user with no role or organization from accessing any viewset. From this point on, you should be able to manage almost everything else using the site's UI.

---

## 5. Run Local Server:
If you're testing on a local machine, to start the server, run:

```bash
python manage.py runserver
```

*or if you want to test mobile with an ExpoGo setup*

```bash
python manage.py runserver 0.0.0.0:8000 #include the IP address so the mobile app can access it
```
