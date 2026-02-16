from flask import Flask, request, render_template, redirect, url_for, jsonify, send_file, session
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
from azure.storage.blob import BlobServiceClient
import pyodbc
import os
import uuid
import requests
from opencensus.ext.azure.log_exporter import AzureLogHandler
import logging
from dotenv import load_dotenv
import threading
import qrcode
from io import BytesIO
import json
from datetime import datetime, timedelta
import pandas as pd
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Azure Blob Setup
blob_service_client = None
container_name = "complaint-images"
try:
    blob_service_client = BlobServiceClient.from_connection_string(os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
    print("Azure Blob Storage client initialized successfully.")
except Exception as e:
    print(f"Warning: Could not initialize Azure Blob Storage: {e}")
    print("The app will continue without blob storage support.")

# Azure SQL Setup
conn_str = os.getenv("AZURE_SQL_CONN_STRING")

# Logic App Webhook URL
logic_app_url = os.getenv("LOGIC_APP_WEBHOOK_URL")

# Monitoring - Azure Application Insights
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
stream_handler.lock = threading.RLock()
logger.addHandler(stream_handler)

appinsights_conn = os.getenv("APPINSIGHTS_CONNECTION_STRING")
if appinsights_conn:
    try:
        ai_handler = AzureLogHandler(connection_string=appinsights_conn)
        ai_handler.lock = threading.RLock()
        logger.addHandler(ai_handler)
    except Exception as e:
        logger.warning("AzureLogHandler could not be added: %s", e)

# Helper Functions
def get_db_connection():
    """Get database connection"""
    return pyodbc.connect(conn_str)

def calculate_priority(title, description):
    """Auto-calculate priority based on keywords"""
    high_priority_keywords = ['urgent', 'emergency', 'critical', 'immediately', 'asap', 'severe']
    medium_priority_keywords = ['important', 'soon', 'attention', 'issue']
    
    text = (title + " " + description).lower()
    
    for keyword in high_priority_keywords:
        if keyword in text:
            return 'High'
    
    for keyword in medium_priority_keywords:
        if keyword in text:
            return 'Medium'
    
    return 'Low'

def award_badges(email):
    """Check and award badges to user"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Count user's complaints
            cursor.execute("SELECT COUNT(*) as count FROM Complaints WHERE email = ?", (email,))
            complaint_count = cursor.fetchone().count
            
            # Get badges user already has
            cursor.execute("SELECT badge_id FROM UserBadges WHERE user_email = ?", (email,))
            earned_badges = [row.badge_id for row in cursor.fetchall()]
            
            # Check badge requirements
            cursor.execute("SELECT id, requirement_type, requirement_value FROM Badges")
            badges = cursor.fetchall()
            
            for badge in badges:
                if badge.id not in earned_badges:
                    if badge.requirement_type == 'complaints_submitted' and complaint_count >= badge.requirement_value:
                        cursor.execute("INSERT INTO UserBadges (user_email, badge_id) VALUES (?, ?)", 
                                     (email, badge.id))
                        conn.commit()
                        socketio.emit('badge_earned', {'email': email, 'badge_id': badge.id}, broadcast=True)
    except Exception as e:
        print(f"Error awarding badges: {e}")

# Routes

@app.route("/")
def home():
    return render_template("landing_page.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Simple role selector from landing page."""
    if request.method == "GET":
        return redirect(url_for("home"))

    role = (request.form.get("role") or "").lower()
    if role == "student":
        session["user_role"] = "student"
        return redirect(url_for("submit_complaint"))
    if role == "admin":
        session["user_role"] = "admin"
        return redirect(url_for("admin_dashboard"))

    return jsonify({"error": "Unknown role"}), 400

@app.route("/submit", methods=["GET", "POST"])
def submit_complaint():
    if request.method == "POST":
        try:
            title = request.form["title"]
            description = request.form["description"]
            type_ = request.form["type"]
            file = request.files.get("file")
            student_name = request.form.get("student_name")
            email = request.form.get("email")
            
            # Calculate priority
            priority = calculate_priority(title, description)
            
            # Calculate due date based on priority
            due_date = None
            if priority == 'High':
                due_date = datetime.now() + timedelta(days=1)
            elif priority == 'Medium':
                due_date = datetime.now() + timedelta(days=3)
            else:
                due_date = datetime.now() + timedelta(days=7)

            file_url = None

            # Upload file to Azure Blob (with timeout)
            if file and file.filename != "" and blob_service_client:
                if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.doc', '.docx')):
                    return jsonify({"success": False, "error": "Invalid file type."}), 400
                file.seek(0, 2)
                if file.tell() > 10 * 1024 * 1024:  # 10MB limit
                    return jsonify({"success": False, "error": "File too large."}), 400
                file.seek(0)
                filename = secure_filename(file.filename)
                blob_name = f"{uuid.uuid4()}_{filename}"
                try:
                    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
                    blob_client.upload_blob(file, timeout=10)  # 10 second timeout
                    file_url = blob_client.url
                except Exception as e:
                    print(f"Warning: Could not upload file to blob storage: {e}")

            # Save to Azure SQL (with error handling)
            complaint_id = None
            try:
                if conn_str:  # Only try if connection string is configured
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO Complaints (title, description, type, file_url, status, student_name, email, priority, due_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (title, description, type_, file_url, "Submitted", student_name, email, priority, due_date))
                        conn.commit()
                        
                        # Get the inserted complaint ID
                        cursor.execute("SELECT @@IDENTITY AS id")
                        complaint_id = cursor.fetchone().id
                        
                        # Log activity (non-blocking)
                        try:
                            cursor.execute("""
                                INSERT INTO ActivityLog (complaint_id, action, performed_by, details)
                                VALUES (?, ?, ?, ?)
                            """, (complaint_id, "Created", student_name, f"Complaint submitted with {priority} priority"))
                            conn.commit()
                        except:
                            pass  # Don't fail if activity log fails
                        
                        # Update user profile (non-blocking)
                        try:
                            cursor.execute("""
                                IF EXISTS (SELECT 1 FROM UserProfiles WHERE email = ?)
                                    UPDATE UserProfiles SET total_complaints = total_complaints + 1, points = points + 10 WHERE email = ?
                                ELSE
                                    INSERT INTO UserProfiles (email, name, total_complaints, points) VALUES (?, ?, 1, 10)
                            """, (email, email, email, student_name))
                            conn.commit()
                        except:
                            pass  # Don't fail if profile update fails
                        
                        # Award badges (non-blocking, in background)
                        try:
                            threading.Thread(target=award_badges, args=(email,), daemon=True).start()
                        except:
                            pass
                else:
                    # If no database, generate a random complaint ID
                    complaint_id = uuid.uuid4().hex[:8].upper()
                    print("Warning: Database not configured, using generated ID")
                    
            except Exception as e:
                logger.error("Error saving to database", exc_info=True)
                # Don't fail completely, generate a complaint ID
                complaint_id = uuid.uuid4().hex[:8].upper()
                print(f"Database error (continuing anyway): {str(e)}")

            # Send Email via Logic App (in background thread to avoid blocking)
            def send_notification():
                try:
                    if logic_app_url:
                        payload = {
                            "title": title,
                            "description": description,
                            "type": type_,
                            "priority": priority,
                            "file_url": file_url,
                            "status": "Submitted",
                            "student_name": student_name,
                            "email": email
                        }
                        requests.post(logic_app_url, json=payload, timeout=2)
                except Exception as e:
                    print(f"Warning: Could not send notification via Logic App: {e}")
            
            threading.Thread(target=send_notification, daemon=True).start()

            # Emit real-time notification
            try:
                socketio.emit('new_complaint', {
                    'id': complaint_id,
                    'title': title,
                    'priority': priority,
                    'status': 'Submitted'
                }, broadcast=True)
            except:
                pass  # Don't fail if socketio fails

            logger.info("Complaint submitted successfully")

            return jsonify({"success": True, "complaint_id": complaint_id})

        except Exception as e:
            logger.error("Error while submitting complaint", exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    return render_template("submit_complaint.html")

@app.route("/admin")
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/profile")
def user_profile():
    return render_template("user_profile.html")

@app.route("/get_complaint/<int:complaint_id>", methods=["GET"])
def get_complaint(complaint_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, type, file_url, status, submitted_at, 
                       priority, rating, upvotes, due_date, student_name, email, resolved_at
                FROM Complaints WHERE id = ?
            """, (complaint_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({"error": "Complaint not found"}), 404
            
            complaint = {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "type": row.type,
                "file_url": row.file_url,
                "status": row.status,
                "priority": row.priority,
                "rating": row.rating,
                "upvotes": row.upvotes,
                "due_date": row.due_date.strftime('%Y-%m-%d %H:%M:%S') if row.due_date else None,
                "submitted_at": row.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if row.submitted_at else "N/A",
                "resolved_at": row.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if row.resolved_at else None,
                "student_name": row.student_name,
                "email": row.email
            }
            
            return jsonify({"complaint": complaint})
    except Exception as e:
        logger.error("Error fetching complaint", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/assign_complaint", methods=["POST"])
def assign_complaint():
    try:
        data = request.get_json()
        complaint_id = data.get("id")
        assignee = data.get("assignee")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Complaints
                SET status = ?, assigned_to = ?
                WHERE id = ?
            """, ("Assigned", assignee, complaint_id))
            
            # Log activity
            cursor.execute("""
                INSERT INTO ActivityLog (complaint_id, action, performed_by, details)
                VALUES (?, ?, ?, ?)
            """, (complaint_id, "Assigned", assignee, f"Assigned to {assignee}"))
            
            conn.commit()

        socketio.emit('status_updated', {'id': complaint_id, 'status': 'Assigned'}, broadcast=True)
        
        return jsonify({"success": True, "message": "Complaint assigned successfully."})
    except Exception as e:
        logger.error("Error assigning complaint", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/update_status", methods=["POST"])
def update_status():
    try:
        data = request.get_json()
        complaint_id = data.get("id")
        new_status = data.get("status")
        performed_by = data.get("performed_by", "Admin")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # If status is Resolved, set resolved_at
            if new_status == "Resolved":
                cursor.execute("""
                    UPDATE Complaints
                    SET status = ?, resolved_at = GETDATE()
                    WHERE id = ?
                """, (new_status, complaint_id))
                
                # Update user profile resolved count
                cursor.execute("""
                    UPDATE UserProfiles 
                    SET resolved_complaints = resolved_complaints + 1, points = points + 50
                    WHERE email = (SELECT email FROM Complaints WHERE id = ?)
                """, (complaint_id,))
            else:
                cursor.execute("""
                    UPDATE Complaints
                    SET status = ?
                    WHERE id = ?
                """, (new_status, complaint_id))
            
            # Log activity
            cursor.execute("""
                INSERT INTO ActivityLog (complaint_id, action, performed_by, details)
                VALUES (?, ?, ?, ?)
            """, (complaint_id, "Status Updated", performed_by, f"Status changed to {new_status}"))
            
            conn.commit()

        socketio.emit('status_updated', {'id': complaint_id, 'status': new_status}, broadcast=True)
        
        return jsonify({"success": True, "message": "Complaint status updated successfully."})
    except Exception as e:
        logger.error("Error updating complaint status", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/rate_complaint", methods=["POST"])
def rate_complaint():
    try:
        data = request.get_json()
        complaint_id = data.get("id")
        rating = data.get("rating")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Complaints SET rating = ? WHERE id = ?", (rating, complaint_id))
            conn.commit()
        
        return jsonify({"success": True, "message": "Rating submitted successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/upvote_complaint", methods=["POST"])
def upvote_complaint():
    try:
        data = request.get_json()
        complaint_id = data.get("id")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE Complaints SET upvotes = upvotes + 1 WHERE id = ?", (complaint_id,))
            conn.commit()
            
            cursor.execute("SELECT upvotes FROM Complaints WHERE id = ?", (complaint_id,))
            upvotes = cursor.fetchone().upvotes
        
        socketio.emit('upvote_updated', {'id': complaint_id, 'upvotes': upvotes}, broadcast=True)
        
        return jsonify({"success": True, "upvotes": upvotes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/comments/<int:complaint_id>", methods=["GET", "POST"])
def manage_comments(complaint_id):
    if request.method == "POST":
        try:
            data = request.get_json()
            user_name = data.get("user_name")
            user_type = data.get("user_type")
            comment_text = data.get("comment_text")
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO Comments (complaint_id, user_name, user_type, comment_text)
                    VALUES (?, ?, ?, ?)
                """, (complaint_id, user_name, user_type, comment_text))
                conn.commit()
                
                cursor.execute("SELECT @@IDENTITY AS id")
                comment_id = cursor.fetchone().id
            
            socketio.emit('new_comment', {
                'complaint_id': complaint_id,
                'user_name': user_name,
                'user_type': user_type,
                'comment_text': comment_text,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, broadcast=True)
            
            return jsonify({"success": True, "comment_id": comment_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, user_name, user_type, comment_text, created_at
                    FROM Comments
                    WHERE complaint_id = ?
                    ORDER BY created_at ASC
                """, (complaint_id,))
                rows = cursor.fetchall()
                
                comments = [{
                    "id": row.id,
                    "user_name": row.user_name,
                    "user_type": row.user_type,
                    "comment_text": row.comment_text,
                    "created_at": row.created_at.strftime('%Y-%m-%d %H:%M:%S')
                } for row in rows]
                
                return jsonify({"comments": comments})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/analytics", methods=["GET"])
def get_analytics():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Total complaints
            cursor.execute("SELECT COUNT(*) as total FROM Complaints")
            total_complaints = cursor.fetchone().total
            
            # By status
            cursor.execute("SELECT status, COUNT(*) as count FROM Complaints GROUP BY status")
            by_status = {row.status: row.count for row in cursor.fetchall()}
            
            # By priority
            cursor.execute("SELECT priority, COUNT(*) as count FROM Complaints GROUP BY priority")
            by_priority = {row.priority: row.count for row in cursor.fetchall()}
            
            # By type
            cursor.execute("SELECT type, COUNT(*) as count FROM Complaints GROUP BY type")
            by_type = {row.type: row.count for row in cursor.fetchall()}
            
            # Average resolution time
            cursor.execute("""
                SELECT AVG(DATEDIFF(hour, submitted_at, resolved_at)) as avg_hours
                FROM Complaints
                WHERE resolved_at IS NOT NULL
            """)
            avg_resolution_hours = cursor.fetchone().avg_hours or 0
            
            # Overdue complaints
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM Complaints
                WHERE due_date < GETDATE() AND status != 'Resolved'
            """)
            overdue_count = cursor.fetchone().count
            
            # Recent activity (last 7 days by day)
            cursor.execute("""
                SELECT CAST(submitted_at AS DATE) as date, COUNT(*) as count
                FROM Complaints
                WHERE submitted_at >= DATEADD(day, -7, GETDATE())
                GROUP BY CAST(submitted_at AS DATE)
                ORDER BY date
            """)
            activity = [{
                "date": row.date.strftime('%Y-%m-%d'),
                "count": row.count
            } for row in cursor.fetchall()]
            
            # Top rated resolutions
            cursor.execute("""
                SELECT TOP 5 title, rating
                FROM Complaints
                WHERE rating IS NOT NULL
                ORDER BY rating DESC
            """)
            top_rated = [{
                "title": row.title,
                "rating": row.rating
            } for row in cursor.fetchall()]
            
            analytics = {
                "total_complaints": total_complaints,
                "by_status": by_status,
                "by_priority": by_priority,
                "by_type": by_type,
                "avg_resolution_hours": round(avg_resolution_hours, 1),
                "overdue_count": overdue_count,
                "activity_7_days": activity,
                "top_rated": top_rated
            }
            
            return jsonify(analytics)
    except Exception as e:
        logger.error("Error fetching analytics", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Top users by points
            cursor.execute("""
                SELECT TOP 10 name, email, points, total_complaints, resolved_complaints
                FROM UserProfiles
                ORDER BY points DESC
            """)
            top_users = [{
                "name": row.name,
                "email": row.email,
                "points": row.points,
                "total_complaints": row.total_complaints,
                "resolved_complaints": row.resolved_complaints
            } for row in cursor.fetchall()]
            
            return jsonify({"leaderboard": top_users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user_profile/<email>", methods=["GET"])
def get_user_profile(email):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get profile
            cursor.execute("""
                SELECT name, email, avatar_url, total_complaints, resolved_complaints, points, created_at
                FROM UserProfiles
                WHERE email = ?
            """, (email,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({"error": "User not found"}), 404
            
            profile = {
                "name": row.name,
                "email": row.email,
                "avatar_url": row.avatar_url,
                "total_complaints": row.total_complaints,
                "resolved_complaints": row.resolved_complaints,
                "points": row.points,
                "created_at": row.created_at.strftime('%Y-%m-%d') if row.created_at else None
            }
            
            # Get badges
            cursor.execute("""
                SELECT b.name, b.description, b.icon, ub.earned_at
                FROM UserBadges ub
                JOIN Badges b ON ub.badge_id = b.id
                WHERE ub.user_email = ?
                ORDER BY ub.earned_at DESC
            """, (email,))
            badges = [{
                "name": row.name,
                "description": row.description,
                "icon": row.icon,
                "earned_at": row.earned_at.strftime('%Y-%m-%d') if row.earned_at else None
            } for row in cursor.fetchall()]
            
            profile["badges"] = badges
            
            return jsonify({"profile": profile})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/activity_log/<int:complaint_id>", methods=["GET"])
def get_activity_log(complaint_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT action, performed_by, details, created_at
                FROM ActivityLog
                WHERE complaint_id = ?
                ORDER BY created_at DESC
            """, (complaint_id,))
            
            activities = [{
                "action": row.action,
                "performed_by": row.performed_by,
                "details": row.details,
                "created_at": row.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for row in cursor.fetchall()]
            
            return jsonify({"activities": activities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/templates", methods=["GET"])
def get_templates():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, category, template_text FROM ResponseTemplates")
            
            templates = [{
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "template_text": row.template_text
            } for row in cursor.fetchall()]
            
            return jsonify({"templates": templates})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/qr/<int:complaint_id>")
def generate_qr(complaint_id):
    """Generate QR code for complaint tracking"""
    try:
        # Create tracking URL
        tracking_url = request.url_root + f"track/{complaint_id}"
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(tracking_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/track/<int:complaint_id>")
def track_complaint(complaint_id):
    """Public complaint tracking page"""
    return render_template("track_complaint.html", complaint_id=complaint_id)

@app.route("/export/excel")
def export_excel():
    """Export complaints to Excel"""
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("""
                SELECT id, title, type, status, priority, student_name, email, 
                       submitted_at, resolved_at, rating
                FROM Complaints
                ORDER BY submitted_at DESC
            """, conn)
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Complaints')
        
        output.seek(0)
        return send_file(output, 
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True,
                        download_name=f'complaints_{datetime.now().strftime("%Y%m%d")}.xlsx')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/export/pdf")
def export_pdf():
    """Export complaints summary to PDF"""
    try:
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 750, "Complaint Management System - Report")
        
        p.setFont("Helvetica", 12)
        p.drawString(100, 720, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get statistics
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM Complaints")
            total = cursor.fetchone().total
            
            cursor.execute("SELECT status, COUNT(*) as count FROM Complaints GROUP BY status")
            status_data = cursor.fetchall()
        
        y = 680
        p.drawString(100, y, f"Total Complaints: {total}")
        y -= 30
        
        p.drawString(100, y, "Status Breakdown:")
        y -= 20
        for row in status_data:
            p.drawString(120, y, f"{row.status}: {row.count}")
            y -= 20
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        return send_file(buffer, 
                        mimetype='application/pdf',
                        as_attachment=True,
                        download_name=f'complaints_report_{datetime.now().strftime("%Y%m%d")}.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Socket.IO Events for Real-time Chat

@socketio.on('join_complaint')
def on_join(data):
    complaint_id = data['complaint_id']
    join_room(f'complaint_{complaint_id}')
    emit('joined', {'complaint_id': complaint_id})

@socketio.on('send_message')
def handle_message(data):
    complaint_id = data['complaint_id']
    sender_name = data['sender_name']
    sender_type = data['sender_type']
    message = data['message']
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ChatMessages (complaint_id, sender_name, sender_type, message)
                VALUES (?, ?, ?, ?)
            """, (complaint_id, sender_name, sender_type, message))
            conn.commit()
        
        emit('new_message', {
            'sender_name': sender_name,
            'sender_type': sender_type,
            'message': message,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }, room=f'complaint_{complaint_id}')
    except Exception as e:
        emit('error', {'message': str(e)})

@socketio.on('typing')
def handle_typing(data):
    complaint_id = data['complaint_id']
    user_name = data['user_name']
    emit('user_typing', {'user_name': user_name}, room=f'complaint_{complaint_id}', include_self=False)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True, allow_unsafe_werkzeug=True)
