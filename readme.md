# WELCOME TO THE BONASO DATA PORTAL SERVER

**Tech stack:** Django 5 + DRF, PostgreSQL 15  
**Auth:** JWT with refresh tokens 
**Deployment:** Dockerized, runs with Gunicorn + Nginx
**Environments:** dev, prod 

## 1. PROJECT OVERVIEW
The BONASO Data Portal is a tool that seeks to enable community health workers and their coordinators capture and analyze various types of client and project data from across the country in real time. The portal is a network of several different tools which work together to collect and retrieve data on the web or on mobile applications. 

This document specifically describes the **frontend website**. For additional context, please also read the documentation for:  
- **Frontend:** BONASO Data Portal Website (Django + PostgreSQL)  
- **Mobile:** BONASO Data Portal Mobile (React Native + Expo)  

The BONASO Data Portal Server is the backend server that controls the flow of information into and out of the database to the end user. Whenever a user records or analyzes data, the backend retrieves it from the database, processes it, and returns it in a format the frontend (web or mobile) can display.

## 2. ARCHITECTURE
PostgreSQL (database)
        ↓
Django (backend / API server)
        ↓
React (frontend / website)
    ↳ Expo + React Native (mobile application)

The backend:
- Is built with **Django**.  
- Sends and collects data via **REST APIs**.  
- Retrieves and stores data in a **PostgreSQL** database. 

Most apps follow a common structure:  
- **ViewSet**: Has list, detail, delete, post, and patch methods. Manages permissions. 
- **Serializers**: Converts data from model instances to JSON, also houses most of the create/update logic. Also manages some create/edit permission logic.  
- **Models**: The schema for the tables in the databases. 
- **Signals**: Automated actions to perform when model instances are created or edited. 
- **Urls**: Contains a list of URL endpoints for the viewsets.
- **Admin**: Contains information for configuring the admin page. We don't really use it sinceit gets kind of complicated with the JWT auth and the frontend, but it can be helpful for dev
- **Utils**: Contains helper functions

See `sitemap.md` for a full outline of apps and features.  

NEXT STEPS:
- Setup: [docs/setup.md]
- Sitemap: [docs/sitemap.md]
- Auth: [docs/auth/md]
