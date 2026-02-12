Colour Creations Archive & Job Tracking System
=============================================

Overview
--------
The Colour Creations Archive & Job Tracking System is a secure internal web application designed and deployed to replace the traditional physical job card archive used in a commercial printing press. The system digitizes job records, enables real-time production tracking and provides structured workflow management across all stages of the printing process.

This application was built to improve operational efficiency, ensure accountability and provide secure, centralized access to job information.

The system is currently deployed and used in a real production environment.


Core Features
-------------

Job Archive Management
- Create and store digital job records
- Assign unique job numbers and serial numbers
- Store customer name, job description, paper details and pricing
- Upload and store multiple job-related images
- Full search functionality by job number, customer name or keywords
- Filter jobs by year and month

Production Job Tracker
- Track jobs through production stages:
  - Designing
  - Plate Processing
  - Press (Printing)
  - Post Press
  - Packing
  - Out for Delivery
  - Delivered
- Record timestamps for each stage update
- Detailed stage history for monitoring delays and workflow progress
- Separate tracker view for live production monitoring

Role-Based Access Control (RBAC)
- Superadmin
  - Full system access
  - Create and delete users
  - Assign roles
  - Access activity logs
- Admin
  - Create, edit, and delete jobs
  - Update tracker stages
  - View activity logs
- Staff
  - Create jobs
  - Update tracker stages
  - Search and view jobs
- Viewer
  - Read-only access

Audit Logging and Accountability
- Logs all system actions including:
  - Job creation
  - Job edits
  - Job deletion
  - Tracker updates
  - User management actions
- Records username, action performed and timestamp

Backup Logbook System
- Allows manual logging of system backups
- Tracks backup history
- Displays next backup due date
- Ensures operational continuity and data protection

Secure Remote Monitoring
- Supports secure remote access via VPN (Tailscale)
- Allows authorized administrators to monitor production remotely
- No public exposure to the internet

Modern Web-Based Interface
- Clean and responsive UI
- Designed for internal network use
- Optimized for operational efficiency in production environments


System Architecture
-------------------

Backend
- Python
- Flask web framework

Database
- SQLite (local persistent storage)

Frontend
- HTML
- CSS
- Bootstrap
- JavaScript

File Storage
- Local image storage system

Security
- Role-based authentication
- Session management
- Activity logging
- Controlled access permissions

Network
- Internal network deployment
- Optional secure remote access via VPN


Purpose and Motivation
----------------------

This system was developed to solve real-world operational problems including:

- Physical job card storage consuming excessive space
- Difficulty tracking job progress in real time
- Lack of accountability for job changes
- Inefficient search and retrieval of past job records
- Limited remote monitoring capability

The system replaces manual processes with a secure, digital solution that improves efficiency, accountability and scalability.


Deployment Environment
----------------------

The application runs on a Windows-based internal server and can be accessed from authorized devices within the network or through secure VPN connection.

The system uses persistent local storage and does not require cloud hosting.


Cybersecurity and Software Engineering Concepts Demonstrated
------------------------------------------------------------

- Secure authentication systems
- Role-based access control implementation
- Audit logging and accountability tracking
- Secure internal application deployment
- File management systems
- Database design and structured data storage
- Real-world production software deployment
- Network security using private VPN access


Author
------

Developed and deployed by:

Isuka Visath Kasthuriarachchi

Cybersecurity Student | Security Enthusiast


Status
------

Production-ready and actively used in a live commercial environment.


License
-------

Private internal system developed for Colour Creations.
