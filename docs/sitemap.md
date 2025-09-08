# BONASO Data Portal: SITEMAP

The following is a basic overview of the server structure and the apps it contains.

---

## Contents:
- [General](#general)
    - [BonasoDataServer](#bonaso_data_server)
    - [Media](#media)
- [Users](#users)
- [Profiles](#profiles)
- [Organizations](#organizations)
- [Indicators](#indicators)
- [Projects](#projects)
- [Respondents](#respondents)
- [Events](#events)
- [Social](#social)
- [Uploads](#uploads)
- [Analysis](#analysis)
- [Flags](#flags)
- [Messaging](#messaging)

---

## General:
### [bonaso_data_server](/bonaso_data_server):

Meta folder that contains high level project information. Most notably:
- [urls.py](/bonaso_data_server/urls.py) → Sets up the app level urls (first layer)
- [settings.py](/bonaso_data_server/settings.py) → Controls high level project settings, including the  database, pagination settings, important auth settings, and some other meta settings. 

### [media](/media/):
Contains uploaded files (primarily from the uploads app)

---

## Users:
**At a glance**: Anything related to user verification, password management, or user creation should live here. But information realted to user profiles (managing names, activity, etc.) should live in [Profiles](#profiles).

**Description**: The users app controls features related to user authentication, including handling our login/logout system, password resets, and user creation. 

[**Important Models**](/users/models.py):
    - User (custom extended user model). Includes the key extension fields of Organization (which organization a user is linked to that manages what content they can see), Client Organization (same thing but specific for the client role), and Role (which sets a user's base permissions).

[**Important Views/Actions**](/users/views.py):
    - ApplyForNewUser: APIView that allows for a user to create another user assuming they have appropriate permissions.
    - AdminResetPasswordView: APIView that allows for an admin to reset a user's password.

**Permissions**: M&E Officers/Managers/Admins/Clients can create users. Clients can only create other clients, while M&E Officers/Managers cannot create clients or admins. Admins can create all.

**Notes**: For more detailed information about authentication rules, please reference [auth.md](/docs/auth.md).

---

## Profiles:
**At a glance:** More superficial aspects of a users account that do not directly relate to authentication.

**Description**: The profiles app houses most features related to the User model that is not explicitly auth related. It is mostly used for:
- Viewing a users profile.
- Editing their username/name/email account
- Viewing user activity (objects created/edited)
- Storing favorites (currently support favorite projects, respondents, and events, but this could be expanded since we use a generic foreign key system)

[**Important Models**](/profiles/models.py):
    - FavoriteObject (generic FK)

[**Important Views/Actions**](/profiles/views.py):
- activity: Custom action on **ProfilesViewSet**. Gets a users activity (as collected by [get_user_activity](/profiles/utils.py))
- get_favorites: Custom action on **ProfilesViewSet**. Gets a list of all of users favorited items.
- is_favorited: Custom action on **ProfilesViewSet**. Checks if a item is favorited, given it is provided an app.model string and an ID number (using [get_favorited_object](/profiles/utils.py)).
- favorite: Custom action on **ProfilesViewSet**. Favorites an item given an app.model string and ID number (using [get_favorited_object](/profiles/utils.py)).
- unfavorite: Custom action on **ProfilesViewSet**. Unfavorites (deletes a favorite instance) an item given an app.model string and an ID number (using [get_favorited_object](/profiles/utils.py)).

**Permissions**: Admins can see/edit any profile. M&E Officers/Managers can edit profiles for their organizaiton/their child orgs. Other roles can only view/edit their own profile. 

**Notes**: [ProfileListSerializer](/profiles/serializers.py) is used in many other serializers for the created_by/updated_by field. 

---

## Organizations:
**At a glance**: Content related to the organization.

**Description**: Organizations are used to help group users together and manage what content they should see (since each user is associated with an organization). Organizations are primarily a permissions helper, but they also contain some contact information and descriptive information about an organization that can be referenced if needed. 

[**Important Models**](/organizations/models.py):
    - Organization: Contains an organization and some basic descriptive information about it. 

**Permissions**: Admins can see all content. M&E Officers/Managers can see content related to their org or their child orgs. Others have no need to see organizations. 

---

## INDICATORS:
**At a glance**: Higher level information about indicators/things the site needs to track.

**Description**: An indicator is any metric that we want this system to track, and serves as the central unifying component of the entire system. 

[**Important Models**](/indicators/models.py):
- Indicator: Contains information about the indicator and its special validation/information requirements.
- Indicator Subcategory: Contains information about indicator subcategories, which is important for matching subcategories and deprecating subcategories. 

**Permissions**: Only admins can create/edit indicators. For the purpose of assigning tasks, M&E Officers/Managers can view indicators for tasks they have been assigned. 

**Notes**:
*Indicator Types*: There are several different types of indicators:
- Respondent: This is an indicator that is meant to be linked directly to one person (or a set of demographic information).
- *Example*: Tested for HIV

- Social: This is an indicator that is meant to be linked directly to a social media post.
- *Example*: Number of People Reached with HIV Prevention Messages on Social Media
- Number of Events: This is an indicator that is tied to an event and automatically counts the number of linked completed events.
- *Example*: Number of Media Engagements Held

- Number of Organizations at Event: This is an indicator that is tied to an event and counts the number of participants (FK organization) at a completed event.
- *Example*: Number of Organizations Trained

 -Counts (do not use): This is a misc. option but will not be pulled in any aggregates. 

*Attached Data*: Indicators are by default just an "it happened", but additional information can be attached:
- Indicators can require a number (toggle the require_numeric boolean).
- *Example*: Number of Lubricants Distributed

- Indicators can require specific subcategories be selected for additional information
- *Example*:: Screened for NCDs → subcategories: BMI, Blood Glucose, Blood Pressure (the user will select which ones apply)
- Subcategories and require a number can be combined.
- *Example*: Number of Condoms Distrubted → subcategories: Male Condom, Female Condom, with a number associated with both male condoms and female condoms

*Managing Subcategories*: Indicator subcategories cannot be removed from an indicator (since this could delete or nullify existing data), so instead if an indicator's subcategories need to be changed, old ones can be deprecated. 

*Validation*: Indicators have some built in validation methods (mostly for respondent type):
- Allow Repeat: If the same person has an interaction associated with the same interaction more than once in 30 days, it will be flagged by default. This boolean will disable that.

- Prerequisites: If an indicator should not be allowed unless prerequisite interactions are had (example, Tested for HIV → Tested Positive for HIV, person should be tested in order to test positive). Setting prerequisites will flag interactions missing a prerequisite.

- Require Attribute: If the respondent undergoing this indicator needs to have a speicifc attribute (example: to complete an interaction with the indicator "People Living With HIV Trained for Self-Defense", the respondent should be a Person Living with HIV).

- Match Subcategories To: If an indicator should share subcategories with a prerequisite, their categories can be explcitly matched, in which case editing subcategories for the parent will automatically reflect in the dependent indicator and the system will throw a flag if the dependent indicator's subcategories are not a subset of the parent.
- *Example*: Screened for NCDs → Referred for NCDs, can share subcategories (BMI, Blood Glucose, Blood Pressure), and shold throw a flag if a person was referred for BMI but not screened for BMI.

*Governs Attribute*: This is a feature still in development, but if an interaction with this indicator is had, it can automatically update certain respondent statuses. Currently on used so that if a respondent has an interaction for "Tested Positive for HIV* their HIV status automatically updates. This could be expanded in the future. 

---

## Projects:
**At a glance**: Information/features that are helpful for organizing data and realted to the project model in some way.

**Description**: The Projects app contains all information related to projects, which are used to segment organization into specific scopes and time periods. 

A Project is required for any data to be collected, since all data recorded is linked to a Task, which needs a project, organization, and indicator. The project itself importatly has a start and end date (outside of which data cannot be recorded for that project). A project can also be assigned a client_organization, which allows users will a client role and that client_organization to view information related to that project.

Projects also house important information about how organizations are related. An organization may be contracted under another organization for the duraiton of a project, and the project app is used to store that relationship. 

[**Important Models**](/projects/models.py):
- Project: Contains basic information about a project
- Task: A nexus model that stores FKs to a project, organization, and an indicator. Any data collected is related to a task. 
- Target: Can set target outcomes for tasks (either as a number or calculated based on the achievement for another task. )
- ProjectOrganization: Primarily a through model for the "organizations" field of projects, but also stores information about different organizations relationships. 
- ProjectActivity: An activity related to a project (such as an M&E check-in or midtern review) that can be scoped to an organization or visible to all members.
- ProjectDeadline: A deadline related to a project.

[**Important Views/Actions**](/projects/views.py):
- assign_child: Custom action in **ProjectViewSet**. Allows a user to assign an organization as a child org (creates a much simpler flow than a complex partial edit logic altering the organizations field on projects).
- promote_org: Custom action in **ProjectViewSet**. Allows an admin to make an organization a top-level organization instead of a child org to another organization.
- remove_organization: Custom action in **ProjectViewSet**. Allows an admin to remove an organization from a project and allows a M&E Officer/Manager to remove a subgrantee from a project (assuming there are no conflicts).
- batch_create_tasks: Custom action in **TaskViewSet**. Takes a project/organization ID and a list of indicator IDs and creates tasks using the [TaskSerializer](/projects/serializers.py).
- mobile_list: Custom action in **TaskViewSet**. Removes pagination and returns all tasks for a user so that the mobile app can get and download all tasks for offline use.
- mark_complete: Custom action in **ProjectDeadlineViewSet**. Allows a user to mark a deadline as completed (even if they may not have edit abilities).

**Permissions**: Only admins can create/edit projects. M&E Officers can view projects, create/edit project acitivities, deadlines, and announcements (assuming they are scoped to their organization), assign subgrantees to their organization (assuming they are not already in the project), and assign tasks/targets for their subgrantees. M&E Officers/Managers cannot assign targets/tasks for their own organization. Clients can view projects they are a client for, but not create any realted materials.  

**Notes**: Projects can also contain useful information for tracking progress. The project app contains deadlines and project activities models that can be used to track important project information. It also contains a targets model that can be used to set targets that an organization should strive to achieve. 

Many project permissions are managed through the ProjectPermHelper class [projects/utils.py] that manages permissions for things like ProjectActivities, ProjectDeadlines, and announcements specific to a project. 

---

## RESPONDENTS:
**At a glance**: Information about people and data collected about them.

**Description**: Respondents contain all information about people stored in our system. A respondent is a person whose data lives in our system. We collect individual respondent profiles that can be used by any organization in any project. Respondents can be linked to tasks (and therefore indicators) through interactions.

**Important Models**:
    - Respondent: A person's demographic profile. 
    - Interaction: A nexus model that connects a respondent to a task (with the respondent indicator type).

**Important Views/Actions**:
    - mobile_upload (respondents) ([respondents/views/respondent_viewset.py] action in RespondentViewSet): Action that can take data from multiple respondents at once and serialize them without making repeated API calls. 
    - mobile_upload (interactions) ([respondents/views/interaction_viewset.py] action in InteractionViewSet): Action that can take data from mutliple interactions as uploaded by the mobile app and serialize them without making repeated API calls.
    - batch_create ([resoondents/views/interaction_viewset.py] action in InteractionViewSet): Takes a list of tasks and associated information and uses them to create interactions without making repeated API calls.
    - get_template ([respondents/views/interaction_viewset.py] action in InteractionViewSet): Generates a downloadable excel template that the user can capture data in and upload it into the system.
    - post_template ([respondents/views/interaction_viewset.py] action in InteractionViewSet): Accepts a template as generated by get_template and converts information in the template into serializable data.

**Notes**: It is worth noting that we allow respondents to remain anonymous, meaning that we only collect general demogrpahic information and no PII, but this makes it harder to track respondents (since no ID number is requested) and protect against duplicates, so this method is of secondary preference. 

*Validation*:
Respondents must be unique, as measured by their ID number (assuming they are not anonymous). 

Respondent IDs are verified and flagged using logic in respondent_flag_check found in [respondents/utils.py]. 

Interactions are verified by their indicator's riles by interaction_flag_check found in [respondents/utils.py].

*Signals*: Editing certain respondent attributes (notable HIV Status, disability status, and kp status) will trigger signals that will automatically set respondent attributes for verification.

If an interaction's indicator governs an attribute, completing that interaction will trigger a signal to change that respondents status (this currently only works for setting HIV status).

---

## EVENTS:
**At a glance**: Information about events that contribute towards project indicators and counts associated with these events. 

**Description**: Events contain information about events and their related counts. Each event has a host organization, can be assigned participants (other organizations who were at the event), and linked tasks. As noted in the indicators app, some linked tasks just need to be linked and they will be automatically calculated. 

**Important Models**:
    - Event: Stores details about an event and associated tasks.
    -Demographic Count: Stores details about counts associated with an event, linked to one task and one event, and then an variable number of demographic fields. 

**Important Views/Actions**:
    -get_breakdowns_meta ([events/views.py], action in EventsViewSet): Returns an object with values/labels for each demographic field optimized for the frontend's count table creation process. 
    - get_counts ([events/views.py], action in EventsViewSet): Returns a list of all counts associated with that event. 
    - update_counts ([events/views.py], action in EventsViewSet): Takes a JSON containing numbers attached to specific demographic splits related to a particular task and stores them in the database. 
    - delete_count ([events.views.py], action in EventsViewSet): Deletes a count (all DemographicCount instances associated with that task for that event.)

**Permissions**: M&E Officers/Managers and admins can create/edit events. M&E Officers/Managers can edit events where they or their child org are the host. Child orgs marked as participants can view the event and edit counts for their tasks in an event. 

**Notes**: Respondent tasks can also be linked to an event, but need an associated count (a number matched with demographic inforation) to be tracked. 

*Validation*: Count flag logic is managed in count_flag_logic at [events/utils.py].

---

## SOCIAL:
**At a glance**: Any data related to social media.

**Description**: The Social app captures information about social media posts. This includes when the post was made, the platform, what tasks it is associated wtih, and any associated metrics. We currently track comments, likes, views, and reach.Metrics can be added or removed, but are hardcoded into the database.

**Important Models**:
- SocialMediaPost: Stores details about a single post on one platform related to any number of tasks. 

**Permissions**: Admins and M&E Officers/Managers can create posts. Posts are not explicitly assigned an organization, so rather permissions are managed via the assigned tasks.

**Notes**: All tasks related to a social media post must be from the same organization. 

---

## UPLOADS:
**At a glance**: Supplemental file uploads that are not meant to directly input information into the system.

**Description**: Uploads are a generic file upload app, mostly meant for managing narrative reports, but could easily be expanded to include other supporting documents. 

**Important Models**:
    - Narrative Report: Stores information about a file and the file itself (.pdf or .docx).

**Important Views/Actions**:
    - download ([uploads/views], action in NarrativeReportViewSet): Allows a user to download an uploaded file.

**Permissions**: Admins can download and upload files for all orgs. Clients can download reports related to their projects. M&E Officers/Managers can upload/download files related to their org or their child orgs. 

**Notes**: Most file uploads should be housed here, but uplaods that are supposed to be linked to a given app (like respondent/interaction Excel uploads) should be stored at that app. This should be mostly for supporting documents that do not interact with the system. 

---

## ANALYSIS:
**At a glance**: Anything related to the aggregation/viewing of data.

**Description**: This app houses all features related to collecting, aggregating, and analyzing data, including dashboards, downloads, and checking target achievement. This is also the location where any APIs that other systems collect data from should be housed. 

Currently, the app can
    - Create Dashboards with charts
    - Create pivot tables (downloadable as a CSV)
    - Create Line Lists (downloadable as a CSV)

**Important Models**:
    - DashboardSettings: Information about a user's dashboard settings.
    - IndicatorChartSettings: Within a dashboard, a specific chart's settings.
    - Pivot Tables: Stores information about a user's pivot table.
    - Line Lists: Stores information about user's line lists.

**Important Views/Actions**:
    - create_update_chart ([analysis/views.py], action in DashboardSettingsViewSet): Takes a JSON object and uses it to update/create settings for a particular dashboard chart.
    - update_chart_filters ([analysis/views.py], action in DashboardSettingsViewSet):Takes a JSON objects a uses it to set filters for a particular chart. 
    - get_breakdowns_meta ([analysis/views.py], action in DashboardSettingsViewSet): Gets a list breakdown fields values/labels that the front end can use when building charts. 
    - download_csv (pivot_tables) ([analysis/views.py], action in TablesViewSet): Downloads a pivot table as a csv file. 
    - download_csv (line_list) ([analysis/views.py], action in LineListViewSet): Downloads a line list as a csv file. 

**Permissions**: Data is available to clients (limited to their own projects), M&E Officers/Managers (limited to their org/child orgs), and admins (see everything). Individual settings for dashboards/line lists/pibot tables are only visible to that user. 

**Notes**:
The utils folder is a little bit intimidating, but basically this is how the aggregation flow works for aggregates:
    1. The aggregates switchboard function ([analysis/utils/aggregates.py]) gets the indicator and then determines what type of data it needs to collect.
    2. The appropriate instances of that object are collected ([analysus/utils/collection.py]).
    3. Depending on the indicator type and what breakdown parameters were supplied, a specialized aggregate function will be run (full list at [analysis/utils/aggregates.py]).
    4. The data can alternatively be converted to a slightly friendlier table format using the prep_csv function at [analysis/utils/csv.py]. This is used when downloading pivot tables.

The target serializer uses methods from [analysis/utils/targets.py] to get target achievements and relative amounts. Note that by default targets also pull achievement from child organizations. 

---

## FLAGS:
**At a glance**: Anyting related to storing information about data validation.

**Description**: Flags is the app that houses information related to tracking potentially suspiscious data. Flags can be generated by users with appropriate permissions (M&E Officers/Managers and Admins) or system generated. Flags can also be automatically resolved if system generated or be resolved by a user after review. 

**Important Models**: 
    - Flag: A generic FK model that is connected to an item and signals it needs to be reviewed.

**Important Views/Actions**:
    - raise_flag ([flags/views.py], action in FlagViewSet): Creates a new flag.
    - resolve_flag ([flags/views.py], action in FlagViewSet): Resolves an existing flag.
    - metadata ([flags/views.py], action in FlagViewSet): Provides metadata about a user's flags. 

**Permissions**: Flags are visible to all, but only createable or resolvable by M&E Officers/Managers and admins. M&E Officers/Managers are restricted to resolving or creating flags for their own instances (excepting respondents).

**Notes**: Instances which have an unresolved flag associated with them will not appear in any aggregates (except line lists, where it is noted in its own column).

When flags are created or resolved, it automatically creates an alert for pertinent parties (see [flags/utils.py])

---

## MESSAGING:
**At a glance**: Anything related to communication between multiple users on the site or between the system and the user.

**Description**: Contains all content related to messages between two users, alerts from the system, or announcements (both general and project scoped).

**Important Models**:
    - Message: A message between two or more people that stores read information and can optionally be assigned as a task. 
    - Announcement: A message designed to be seen by many people (though can be scoped to projects/organizations).
    - Alert: System generated messages, currently only created when flags are created/resolved.

**Important Views/Actions**:
    - set_completed ([messaging/views.py], action in MessagesViewSet): Marks a message that was assigned as a task as completed.
    - get_recipients ([messaging.views.py], action in MessagesViewSet): Gets a list of recipients or a user based on their role/organization (since default profile permissions may be restricted for non-admins).

**Permissions**: M&E Officers/Managers can message anyone in their organization or at their child orgs. Other roles are restricted to just users from their organization/client_organization (for clients). All users can message any admin. Admins can message all. 

M&E Officers/Managers can only send announcements for a specific project that is only visible to their org/child orgs. Admins can create sitewide announcements. 

Messages are only visible to people in the thread (not even admins can see other people's messages).

**Notes**: 
Messages, announcements, and alerts all have read statuses and custom actions to mark them as read. 

Announcements can be scoped to projects, admins can create general announcements for the whole site. 