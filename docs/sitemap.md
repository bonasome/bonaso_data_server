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
- [Aggregates](#aggregates)
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
- FavoriteObject (generic FK): Takes a content type and an object id and stores it as a "favorited" object that can be sent to the frontend to provide a quick link to that object.

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

## Indicators:
**At a glance**: Higher level information about indicators/things the site needs to track. Can be either "standalone" for things like events, social media posts, or miscellanous indicators, or be grouped into an assessment if they are meant to be linked to a respondent. 

**Description**: An indicator is any metric that we want this system to track, and serves as the central unifying component of the entire system. 

[**Important Models**](/indicators/models.py):
- Indicator: Contains information about the indicator and its special validation/information requirements.
- Assessment: Contains an assessment, which is essentially a grouping of indicators that are meant to be answered in a sequential order during "one session."
- Option: Linked to an indicator, allows for additional information to be attached to a response.
- LogicGroup: A group of logic linked to a question that contains an operator for the conditions.
- LogicCondition: Linked to a group, this is a condition that can either be linked to a previous indicator in the assessment or a respondent field. Determines if the question should be answerable. 

**Permissions**: Only admins can create/edit indicators and assessments. For the purpose of assigning tasks and analyzing data, M&E Officers/Managers can view indicators for tasks they have been assigned. 

**Notes**:

*Indicator Categories*: There are several different categories of indicators:
- Assessment: This is an indicator is meant to be housed in an assessment and linked to a respondent via a response/interaction.
    - *Example*: Tested for HIV, Tested Positive for HIV

- Social: This is an indicator that is meant to be linked directly to a social media post.
    - *Example*: Number of People Reached with HIV Prevention Messages on Social Media
- Number of Events: This is an indicator that is tied to an event and automatically counts the number of linked completed events.
    - *Example*: Number of Media Engagements Held

- Organizations Capacitated: This is an indicator that is tied to an event and counts the number of participants (FK organization) at a completed event.
    - *Example*: Number of Organizations Trained

- Misc : This is designed as a misc. option that a user can enter aggregated data for. Used for one-off things. 

*Assessment Indicators*: Assessment indicators can have different types:
    - Yes/No: The user can give a boolean response (true/false)
    - Number: The user can enter an integer.
    - Open Text: The user can enter any text.
    - Multiselect: The user can select any number of options
    - Single Select: The user can select one option.
    - Numbers by Category: The user can enter numbers for a defined set of options. 

Assessment indicators can also be selected to allow for aggregate reporting. They can also be marked as optional or required. Mutliselect/single select options can also allow none options. If a user responds none, this information will be treated as though the user did not answer the question, but it is helpful for managing logic and managing requirements (basically determining the difference between this user has not gotten to this question versus this question was deliberately left blank). Multiselect indicators can also match options with a previous indicator, in which case what options a user selected for the previous indicator will be mirrorred for this indicator, and this indicator's options will be filtered based on the previous indicators selected options. 

---

## Projects:
**At a glance**: Information/features that are helpful for organizing data and realted to the project model in some way.

**Description**: The Projects app contains all information related to projects, which are used to scope data to specific funders/time periods. 

A Project is required for any data to be collected, since all data recorded is linked to a Task, which needs a project, organization, and indicator. The project itself importatly has a start and end date (outside of which data cannot be recorded for that project). A project can also be assigned a client_organization, which allows users will a client role and that client_organization to view information related to that project.

Projects also house important information about how organizations are related. An organization may be contracted under another organization for the duraiton of a project, and the project app is used to store that relationship. 

[**Important Models**](/projects/models.py):
- Project: Contains basic information about a project.
- Task: A nexus model that stores FKs to a project, organization, and an indicator. Any data collected is related to a task. 
- Target: Can set target outcomes for tasks (either as a number or calculated based on the achievement for another task).
- ProjectOrganization: Primarily a through model for the "organizations" field of projects, but also stores information about different organizations relationships (parent and child). 
- ProjectDeadline: A deadline related to a project.

[**Important Views/Actions**](/projects/views.py):
- assign_child: Custom action in **ProjectViewSet**. Allows a user to assign an organization as a child org (creates a much simpler flow than a complex partial edit logic altering the organizations field on projects).
- promote_org: Custom action in **ProjectViewSet**. Allows an admin to make an organization a top-level organization instead of a child org to another organization.
- remove_organization: Custom action in **ProjectViewSet**. Allows an admin to remove an organization from a project and allows a M&E Officer/Manager to remove a subgrantee from a project (assuming there are no conflicts).
- batch_create_tasks: Custom action in **TaskViewSet**. Takes a project/organization ID and a list of indicator IDs and creates tasks using the [TaskSerializer](/projects/serializers.py).
- mobile_list: Custom action in **TaskViewSet**. Removes pagination and returns all tasks (with an assessment) for a user so that the mobile app can get and download all tasks for offline use.
- mark_complete: Custom action in **ProjectDeadlineViewSet**. Allows a user to mark a deadline as completed (even if they may not have edit abilities).

**Permissions**: Only admins can create/edit projects. M&E Officers can view projects, create/edit project acitivities, deadlines, and announcements (assuming they are scoped to their organization), assign subgrantees to their organization (assuming they are not already in the project), and assign tasks/targets for their subgrantees. M&E Officers/Managers cannot assign targets/tasks for their own organization. Clients can view projects they are a client for, but not create any realted materials.  

**Notes**: Projects can also contain useful information for tracking progress. The project app contains deadlines and project activities models that can be used to track important project information. It also contains a targets model that can be used to set targets that an organization should strive to achieve. 

Many project permissions are managed through the ProjectPermHelper class [utils.py](/projects/utils.py) that manages permissions for things like ProjectActivities, ProjectDeadlines, and announcements specific to a project. 

Information about target achievement references util functions in the [analysis](/analysis/utils/targets.py).

---

## Respondents:
**At a glance**: Information about people and data collected about them.

**Description**: Respondents contain all information about people stored in our system. A respondent is a person whose data lives in our system. We collect individual respondent profiles that can be used by any organization in any project (to prevent duplicates and allow for tracking people's history interacting with healthcare organizations). Respondents can be linked to tasks (and therefore indicators) through interactions.

[**Important Models**](/respondents/models.py):
- Respondent: A person's demographic profile. 
- Interaction: A nexus model that connects a respondent to a task (with an assessment).
- Response: Linked to an interaction and an indicator. Contains the response to that indicator, either as a boolean, text/number, or an fk to an option. Mutliselect/MultiInt types store in multiple rows. 

**Important Views/Actions**:
- [mobile_upload](/respondents/views/respondent_viewset.py): Custom action in **RespondentViewSet**. Action that can take data from multiple respondents at once and serialize them without making repeated API calls. 
- [mobile_upload](/respondents/views/interaction_viewset.py): Custom action in **InteractionViewSet**. Action that can take data from mutliple interactions as uploaded by the mobile app and serialize them without making repeated API calls.
- [get_template](/respondents/views/interaction_viewset.py) Custom action in **InteractionViewSet**. Generates a downloadable excel template that the user can capture data in and upload it into the system.
- [post_template](/respondents/views/interaction_viewset.py): Custom action in InteractionViewSet. Accepts a template as generated by get_template and converts information in the template into serializable data.

**Notes**: It is worth noting that we allow respondents to remain anonymous, meaning that we only collect general demogrpahic information and no PII, but this makes it harder to track respondents (since no ID number is requested) and protect against duplicates, so this method is of secondary preference. 

Note that assessment logic checks for creating interactions are housed in the [utils](/respondents/utils.py) file.

*Validation*:
Respondents must be unique, as measured by their ID number (assuming they are not anonymous). 

Respondent IDs are verified and flagged using logic in [respondent_flag_check](/respondents/utils.py). 

Interactions/Responses must follow assessment logic [check_logic](/respondents/utils.py)

If an interaction's indicator governs an attribute, completing that interaction will trigger a signal to change that respondents status (this currently only works for setting HIV status).

---
## Aggregates:
**At a glance**: Allows a user to record data in aggregated format, without having to link it to a respondent in the system. Ideally this system is only used as a backup/transition tool, secondary to the main method of creating a respondent and an interaction. 

**Description**: Aggregates allow a user to enter data in a tabular format without being directly linked to a respondent. The user can select from any number of breakdown categories (sex, age range, etc.) to disaggregate the data. These numbers will be pulled when running analysis (unless the count is flagged).

[**Important Models](/aggregates/models.py):
- AggregateGroup: Has information about a group of aggregates, such as project, indicator, organization, and time period. 
- AggregateCount: Contains a "row" of data, with any of the disaggregation fields the user selected and a value. Linked to an aggregate group.

**Permissions**: M&E Officers/Managers and admins can create/edit aggregates. Clients are allowed to view counts linked to a project they are a client of. 

**Notes**: Only indicators that are flagged with allow_aggregate can be used for aggregates. If the source indicator was part of an assessment, the system will try to employ the assessment logic and create flags (i.e. flag if referred was higher than screened). 

If an indicator has options, those are automatically included in the disaggregation fields. 

For multiselect questions, a "Total" row will be automatically created, to allow the user to enter the number of unique people regardless of category.

---

## Events:
**At a glance**: Information about events that contribute towards project indicators and counts associated with these events. 

**Description**: Events contain information about events and their related counts. Each event has a host organization, can be assigned participants (other organizations who were at the event), and linked tasks. As noted in the indicators app, some tasks of the "Number of Events" or "Organizations Capacitated" just need to be linked to the event and they will be automatically calculated.

[**Important Models**](/events/models.py):
- Event: Stores details about an event and associated tasks.

**Permissions**: M&E Officers/Managers and admins can create/edit events. M&E Officers/Managers can edit events where they or their child org are the host.

**Notes**: Tasks with indicator categories of Event No/Orgs Capacitated can be linked directly to an event and will automatically count towards targets/be pulled for analytics.

---

## Social:
**At a glance**: Any data related to social media posts.

**Description**: The Social app captures information about social media posts. This includes when the post was made, the platform, what tasks it is associated with, and any associated metrics. We currently track comments, likes, views, and reach. Metrics can be added or removed, but are hardcoded into the database, and if changed, those changes will need to be reflected in [aggregates](/analysis/utils/aggregates.py).

[**Important Models**](/social/models.py):
- SocialMediaPost: Stores details about a single post on one platform related to any number of tasks. 

**Permissions**: Admins and M&E Officers/Managers can create posts. Posts are not explicitly assigned an organization, so rather permissions are managed via the assigned tasks (all tasks linked to a post must be from the same organization).

**Notes**: All tasks related to a social media post must be from the same organization. Posts can be flagged, but only by a user, the system will never flag a post.

*Future Expansion*: In the future we could look into getting post data via API calls so they do not need to be updated manually.

---

## Uploads:
**At a glance**: Supplemental file uploads that are not meant to directly input information into the system.

**Description**: Uploads are a generic file upload app, mostly meant for managing narrative reports, but could easily be expanded to include other supporting documents. 

[**Important Models**](/uploads/models.py):
- Narrative Report: Stores information about a file and the file itself (.pdf or .docx).

[**Important Views/Actions**](/uploads/views.py):
- download: Custom action in **NarrativeReportViewSet**. Allows a user to download an uploaded file.

**Permissions**: Admins can download and upload files for all orgs. Clients can download reports related to their projects. M&E Officers/Managers can upload/download files related to their org or their child orgs. 

**Notes**: Most file uploads should be housed here, but uplaods that are supposed to be linked to a given app (like respondent/interaction Excel uploads) should be stored at that app. This should be mostly for supporting documents that do not interact with the system. 

---

## Analysis:
**At a glance**: Anything related to the aggregation/viewing of data.

**Description**: This app houses all features related to collecting, aggregating, and analyzing data, including dashboards, downloads, and checking target achievement. This is also probably the location where any APIs that other systems collect data from should be housed. 

Currently, the app can
- Create Dashboards with charts
- Create pivot tables (downloadable as a CSV)
- Create Line Lists (downloadable as a CSV)

[**Important Models**](/analysis/models.py):
- DashboardSettings: Information about a user's dashboard settings.
- IndicatorChartSettings: Within a dashboard, a specific chart's settings.
- Pivot Tables: Stores information about a user's pivot table.
- Line Lists: Stores information about user's line lists.

[**Important Views/Actions**](/analysis/views.py):
- create_update_chart: Custom action in **DashboardSettingsViewSet**. Takes a JSON object and uses it to update/create settings for a particular dashboard chart.
- update_chart_filters: Custom action in **DashboardSettingsViewSet**. Takes a JSON objects a uses it to set filters for a particular chart. 
- get_breakdowns_meta: Custom action in **DashboardSettingsViewSet**. Gets a list breakdown fields values/labels that the front end can use when building charts. 
- download_csv: Custom action in **TablesViewSet**. Downloads a user created pivot table as a csv file. 
- download_csv: Custom action in **LineListViewSet**. Downloads a user created line list as a csv file. 

**Permissions**: Data is available to clients (limited to their own projects), M&E Officers/Managers (limited to their org/child orgs), and admins (see everything). Individual settings for dashboards/line lists/pibot tables are only visible to that user. 

**Notes**:
The utils folder is a little bit intimidating, but basically this is how the aggregation flow works for aggregates:
1. The aggregates switchboard [function](/analysis/utils/aggregates.py) gets the indicator and then determines what type of data it needs to collect.
2. The appropriate instances of that object based on the criteria/user permissions are collected with the appropriate collector [function](/analysis/utils/collection.py).
3. Depending on the indicator type and what breakdown parameters were supplied, a specialized aggregate [function](/analysis/utils/aggregates.py) will be run.
4. The data is sent as an object with positional keys by default. It can alternatively be converted to a slightly friendlier table format using the [prep_csv](/analysis/utils/csv.py). This is used when constructing/downloading pivot tables.

The [TargetSerializer](/projects/serializers.py) uses methods from this app's [utils](/analysis/utils/targets.py) folder to get target achievements and relative amounts. Note that by default targets also pull achievement from child organizations. 

If a question type is numeric, we support averages. We can also track "repeats", i.e., the respondent has had an interaction with this assessment n number of times.
---

## Flags:
**At a glance**: Anyting related to storing information about data validation.

**Description**: Flags is the app that houses information related to tracking potentially suspiscious data. Flags can be generated by users with appropriate permissions (M&E Officers/Managers and Admins) or system generated. Flags can also be automatically resolved if system generated or be resolved by a user after review.

*As of now, flags are currently attachable to respondent instances, interaction instances, demograpic count instances, and social media post instances*.

[**Important Models**](/flags/models.py): 
- Flag: A generic FK model that is connected to an item and signals it needs to be reviewed.

[**Important Views/Actions**](/flags/views.py):
- raise_flag: Custom action in **FlagViewSet**. Used by a user to create a new flag.
- resolve_flag: Custom action in **FlagViewSet**. Used by a user to resolve an existing flag (user or system generated).
- metadata: Custom action in **FlagViewSet**. Provides metadata about a user's flags. 

**Permissions**: Flags are visible to all, but only createable or resolvable by M&E Officers/Managers and admins. M&E Officers/Managers are restricted to resolving or creating flags for their own instances (excepting respondents).

**Notes**: Instances which have an unresolved flag associated with them will not appear in any aggregates (except line lists, where it is noted in its own column).

When flags are created or resolved, it automatically creates an [alert](/flags/utils.py) for pertinent parties.

---

## Messaging:
**At a glance**: Anything related to communication between multiple users on the site or between the system and the user.

**Description**: Contains all content related to messages between two users, alerts from the system, or announcements (both general and project scoped).

[**Important Models**](/messaging/models.py):
- Message: A message between two or more people that stores read information and can optionally be assigned as a task. 
- Announcement: A message designed to be seen by many people (though can be scoped to projects/organizations).
- Alert: System generated messages, currently only created when flags are created/resolved.

[**Important Views/Actions**](/messaging/views.py):
- set_read: Custom action in **MessagesViewSet**. Marks a MessageRecipient as read (for a specific message/user combo).
- set_completed: Custom action in **MessagesViewSet**. Marks a message that was assigned as a task as completed.
- get_recipients: Custom action in **MessagesViewSet**. Gets a list of recipients or a user based on their role/organization (since default profile permissions may be restricted for non-admins).

**Permissions**: M&E Officers/Managers can message anyone in their organization or at their child orgs. Other roles are restricted to just users from their organization/client_organization (for clients). All users can message any admin. Admins can message all. 

M&E Officers/Managers can only send announcements for a specific project, and it will only be visible to their org/child orgs. Admins can create sitewide announcements. 

Messages are only visible to people in the thread (not even admins can see other people's messages).

**Notes**: 

Messages, announcements, and alerts all have read statuses and custom actions to mark them as read. 

Announcements can be scoped to projects, admins can create general announcements for the whole site. 