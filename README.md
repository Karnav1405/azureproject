# 🚀 Smart Complaint Management System

A comprehensive, feature-rich complaint management system built with Flask and Azure services. Perfect for educational institutions, corporate help desks, or customer service platforms.

## ✨ Key Features

### Core Features
- 📝 Submit complaints with file attachments
- 👥 Separate dashboards for students and administrators
- 🔄 Real-time updates using Socket.IO
- ⚡ Auto-priority detection based on keywords
- ⭐ Rating and upvoting system
- 💬 Comments and discussions on complaints
- 🏆 Gamification with badges and leaderboard
- 📊 Analytics dashboard with charts
- 🔍 Advanced search and filtering
- 📥 Export to Excel and PDF
- 📱 QR code generation for each complaint
- 🌙 Dark mode support
- 🎤 Voice input for complaint descriptions
- 📎 Drag & drop file uploads

### Technical Features
- Azure SQL Database integration
- Azure Blob Storage for file uploads
- Azure Logic Apps for notifications
- Azure Application Insights for monitoring
- Real-time bidirectional communication
- Responsive mobile-friendly design

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Azure account with SQL Database and Blob Storage
- VS Code (recommended)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/Karnav1405/azureproject.git
cd azureproject
```

2. **Create virtual environment:**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
Create a `.env` file with:
```env
AZURE_STORAGE_CONNECTION_STRING=your_connection_string
AZURE_SQL_CONN_STRING=your_sql_connection_string
LOGIC_APP_WEBHOOK_URL=your_logic_app_url
APPINSIGHTS_CONNECTION_STRING=your_appinsights_connection
FLASK_SECRET_KEY=your_secret_key
```

5. **Setup database:**
Run `schema.sql` in your Azure SQL Database to create all necessary tables.

6. **Run the application:**
```bash
python app.py
```

7. **Access the app:**
- Main page: http://localhost:5000
- Admin dashboard: http://localhost:5000/admin
- Student dashboard: http://localhost:5000/dashboard

## 📚 Documentation

See [FEATURES.md](FEATURES.md) for comprehensive feature documentation and API reference.

## 🛠️ Tech Stack

- **Backend:** Flask, Flask-SocketIO
- **Database:** Azure SQL Database
- **Storage:** Azure Blob Storage
- **Monitoring:** Azure Application Insights
- **Automation:** Azure Logic Apps
- **Frontend:** HTML5, CSS3, JavaScript, Socket.IO
- **Libraries:** Pandas, OpenPyXL, ReportLab, QRCode

## 📊 Project Structure

```
azureproject/
├── app.py                 # Enhanced main application
├── app_backup.py          # Original backup
├── schema.sql             # Database schema
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── templates/             # HTML templates
│   ├── submit_complaint.html
│   ├── admin_dashboard.html
│   ├── student_dashboard.html
│   ├── landing_page.html
│   ├── user_profile.html
│   └── track_complaint.html
├── FEATURES.md            # Feature documentation
└── README.md              # This file
```

## 🎯 Use Cases

- **Educational Institutions**: Student complaint management
- **Corporate Help Desk**: Employee support tickets
- **Customer Service**: Customer complaint tracking
- **Facility Management**: Maintenance requests
- **IT Support**: Technical issue tracking

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the MIT License.

## 👥 Authors

- Karnav1405 - Initial work

## 🙏 Acknowledgments

- Azure for cloud services
- Flask community for excellent framework
- All contributors and testers

## 📞 Support

For support, email your-email@example.com or open an issue on GitHub.

---

Made with ❤️ for better complaint management