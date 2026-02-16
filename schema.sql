-- Enhanced Database Schema for Smart Complaint System

-- Main Complaints Table Enhancement
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'Complaints') AND name = 'priority')
BEGIN
    ALTER TABLE Complaints ADD priority VARCHAR(20) DEFAULT 'Medium';
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'Complaints') AND name = 'rating')
BEGIN
    ALTER TABLE Complaints ADD rating INT NULL;
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'Complaints') AND name = 'upvotes')
BEGIN
    ALTER TABLE Complaints ADD upvotes INT DEFAULT 0;
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'Complaints') AND name = 'due_date')
BEGIN
    ALTER TABLE Complaints ADD due_date DATETIME NULL;
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID(N'Complaints') AND name = 'resolved_at')
BEGIN
    ALTER TABLE Complaints ADD resolved_at DATETIME NULL;
END
GO

-- Comments Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Comments')
BEGIN
    CREATE TABLE Comments (
        id INT PRIMARY KEY IDENTITY(1,1),
        complaint_id INT FOREIGN KEY REFERENCES Complaints(id),
        user_name VARCHAR(255),
        user_type VARCHAR(50),
        comment_text TEXT,
        created_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- User Profiles Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserProfiles')
BEGIN
    CREATE TABLE UserProfiles (
        id INT PRIMARY KEY IDENTITY(1,1),
        email VARCHAR(255) UNIQUE,
        name VARCHAR(255),
        avatar_url VARCHAR(500),
        total_complaints INT DEFAULT 0,
        resolved_complaints INT DEFAULT 0,
        points INT DEFAULT 0,
        created_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- Badges Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Badges')
BEGIN
    CREATE TABLE Badges (
        id INT PRIMARY KEY IDENTITY(1,1),
        name VARCHAR(100),
        description VARCHAR(255),
        icon VARCHAR(50),
        requirement_type VARCHAR(50),
        requirement_value INT
    );
    
    INSERT INTO Badges (name, description, icon, requirement_type, requirement_value)
    VALUES 
        ('First Complaint', 'Submitted your first complaint', '🎯', 'complaints_submitted', 1),
        ('Active Reporter', 'Submitted 10 complaints', '⭐', 'complaints_submitted', 10),
        ('Power User', 'Submitted 50 complaints', '🔥', 'complaints_submitted', 50),
        ('Quick Resolver', 'Resolved 10 complaints in 24 hours', '⚡', 'quick_resolutions', 10),
        ('Problem Solver', 'Resolved 100 complaints', '🏆', 'complaints_resolved', 100);
END
GO

-- User Badges Junction Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserBadges')
BEGIN
    CREATE TABLE UserBadges (
        id INT PRIMARY KEY IDENTITY(1,1),
        user_email VARCHAR(255),
        badge_id INT FOREIGN KEY REFERENCES Badges(id),
        earned_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- Chat Messages Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ChatMessages')
BEGIN
    CREATE TABLE ChatMessages (
        id INT PRIMARY KEY IDENTITY(1,1),
        complaint_id INT FOREIGN KEY REFERENCES Complaints(id),
        sender_name VARCHAR(255),
        sender_type VARCHAR(50),
        message TEXT,
        is_read BIT DEFAULT 0,
        created_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- Notification Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Notifications')
BEGIN
    CREATE TABLE Notifications (
        id INT PRIMARY KEY IDENTITY(1,1),
        user_email VARCHAR(255),
        title VARCHAR(255),
        message TEXT,
        type VARCHAR(50),
        is_read BIT DEFAULT 0,
        created_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- Activity Log Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ActivityLog')
BEGIN
    CREATE TABLE ActivityLog (
        id INT PRIMARY KEY IDENTITY(1,1),
        complaint_id INT FOREIGN KEY REFERENCES Complaints(id),
        action VARCHAR(100),
        performed_by VARCHAR(255),
        details TEXT,
        created_at DATETIME DEFAULT GETDATE()
    );
END
GO

-- Response Templates Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ResponseTemplates')
BEGIN
    CREATE TABLE ResponseTemplates (
        id INT PRIMARY KEY IDENTITY(1,1),
        title VARCHAR(255),
        category VARCHAR(100),
        template_text TEXT,
        created_by VARCHAR(255),
        created_at DATETIME DEFAULT GETDATE()
    );
    
    INSERT INTO ResponseTemplates (title, category, template_text, created_by)
    VALUES 
        ('Issue Received', 'Acknowledgment', 'Thank you for reporting this issue. We have received your complaint and our team will look into it shortly.', 'system'),
        ('Under Investigation', 'Update', 'We are currently investigating your complaint. We will update you once we have more information.', 'system'),
        ('Issue Resolved', 'Resolution', 'Your complaint has been resolved. Please check and confirm if the issue is fixed. Thank you for your patience.', 'system'),
        ('Need More Info', 'Query', 'We need additional information to process your complaint. Please provide more details about the issue.', 'system');
END
GO
