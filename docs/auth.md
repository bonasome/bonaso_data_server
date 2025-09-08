# BONASO Data Portal Server: Authentication Rules

Almost all of our authentication logic is housed within the Users app. 
-The general rule is to protect access closely. We deal with a lot of sensitive information, and so security is key. 
- Users without login credentials should be completely barred from accessing anything.
- Careful consideration should be assigned to what users can view what content they can create or edit. 

---

## Authentication Flow

The basic auth flow is as follows:
1. The user logs in with a **username** and **password**.
2. The server issues an access and a refresh token.
3. After 5 minutes the access token expires, but the refresh token can fetch another access token.
4. After 8 hours the refresh token expires and the user must log in again.

Note that refresh tokens are blacklisted using SimpleJWTs blacklist functions (more info [here](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/blacklist_app.html)).

**Website Logic**
User logs in → 
server issues access + refresh tokens (in HTTP-only cookies) → 
frontend sends requests with cookies → 
server validates tokens (tokens are blacklisted)

**Mobile Logic**
User logs in via MobileLoginView → 
server returns access + refresh tokens in JSON → 
mobile stores tokens in secure storage → 
mobile uses access token in headers → 
refresh via MobileRefreshView (tokens are blacklisted)

The mobile app does work with cookies, so here we use two seperate views (MobileLoginView and MobileRefreshView, the latter does send JSON tokens). These endpoints ('mobile-login' and 'mobile_token_refresh') should only be used when designing applications that cannot support HTTP cookies. 

Almost every endpoint is protected, and will require a valid access token to manage. 

For the website, we use a HTTP Cookie JWT auth system, meaning the access and refresh tokens are sent via cookies (not in the JSON data). 

---

## User Model
It is important to note a couple important extensions to the user model:

**Organization**: FK to Organization; determines data scope & permission.

**Client Organization**: FK to Client; works similarly in principle to an organization in determining scope/permission

**Role**: Custom string-based role (not Django Groups/Permissions):

| Category | Admin (Site Administrator) | M&E Officer/Manager | Data Collector | Client |
|---|---|---|---|---|
|Role Overview| Full access to view, create, and destroy anything. | Access to view/create content related to the user's organization and their child organizations | Access to create interactions for their own organization (not child orgs, however) | Able to view all data related to projects they are the client on, but virtually no create/destroy privlleges |
| User Creation Perms | Can create/edit/view users of any role | Can create/view M&E Officers/Managers and Data Collectors for their organization or their child organizations (but cannot edit their roles, and creation must be approved by an admin as they will be inactive by default) | Cannot create users | Can create but not view other client viewers within the same client organization | 

- *(Not in use) Supervisor*: TBD role, do not assign
- *(Not in use) View Only*: Placeholder role, blocks access to the site

---

## Custom Auth Rules
It's also important to note that there are a couple other custom auth features:

- [**Role Restricted Views**](/users/restrictviewset.py): This site relies a lot on roles/organizations to manage permissions, and therefore it is assumed that every user has a role and organization. If they do not, while they will be allowed to log in, they will not be allowed to access any viewsets (you can see that almost all viewsets inherit from this custom Viewset extension).

- [**Inactive Users**](/users/permissions.py): If a user is not active, we deny them permission when checking IsAuthenticated, and therefore they effectively are not allowed to log in. 

---

## User Creation Flow
At the moment, since this is mostly being built for the pilot and we want to tightly restrict access, our user creation flow looks like this:
1. User created by:
    - Client → may only create Clients
    - M&E Officer/Manager → may create M&E Officers/Managers, Supervisors, Data Collectors
    - Admin → may create any role
2. All new users are inactive by default
3. Admin must activate account manually before login is possible

---

## Password Management
- **Preferred**: Email reset flow (requires mail server)
- **Fallback**: Admin resets password (cannot view password, only reset)