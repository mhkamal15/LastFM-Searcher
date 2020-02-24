#!/usr/bin/env python3

import sys, ctypes

from fbs_runtime.application_context.PyQt5 import ApplicationContext

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox, QGraphicsScene, QDialog
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5 import uic
from requests import get
from re import search

CF_UNICODETEXT = 13

kernel32 = ctypes.windll.kernel32
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32 = ctypes.windll.user32
user32.GetClipboardData.restype = ctypes.c_void_p

class Settings(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(appctxt.get_resource('settings.ui'), self)
        self.settings = QSettings('WCYT', 'Last FM Searcher')
        self.monitor_clipboard_checkbox.setChecked(self.monitor_clipboard)
        self.auto_search_checkbox.setChecked(self.auto_search)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def accept(self):
        self.monitor_clipboard = self.monitor_clipboard_checkbox.isChecked()
        self.auto_search = self.auto_search_checkbox.isChecked()
        self.hide()

    def reject(self):
        self.monitor_clipboard_checkbox.setChecked(self.monitor_clipboard)
        self.auto_search_checkbox.setChecked(self.auto_search)
        self.hide()

    @property
    def monitor_clipboard(self):
        return self.settings.value('monitor_clipboard', 'true') == 'true'
    
    @monitor_clipboard.setter
    def monitor_clipboard(self, value):
        self.settings.setValue('monitor_clipboard', value)
        self.monitor_clipboard_checkbox.setChecked(value)
    
    @property
    def auto_search(self):
        return self.settings.value('auto_search', 'true') == 'true'
    
    @auto_search.setter
    def auto_search(self, value):
        self.settings.setValue('auto_search', value)
        self.auto_search_checkbox.setChecked(value)

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(appctxt.get_resource('main.ui'), self)
        self.info.hide()

        self.search_button.clicked.connect(self.search)
        self.track.returnPressed.connect(self.search)
        self.artist.returnPressed.connect(self.search)
        self.mbid.returnPressed.connect(self.search)

        self.album.setScene(QGraphicsScene())
        self.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.query_clipboard_changes)
        self.timer.start(500)

        self.settings = Settings(self)
        self.settings_button.clicked.connect(self.show_settings)

        self.last_text = self.get_clipboard_text()
    
    def search(self):
        track = self.track.text().strip()
        artist = self.artist.text().strip()
        mbid = self.mbid.text().strip()
        if not mbid and (track == '' or artist == ''):
            return QMessageBox.warning(self, 'Error', 'Either a track and artist or a musicbrainz id are required.', QMessageBox.Ok)
        params = {}
        if track: params['track'] = track
        if artist: params['artist'] = artist
        if mbid: params['mbid'] = mbid
        self.search_button.setDisabled(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.found_label.setText('Searching...')
        self.info_detail.hide()
        self.info.show()
        self.repaint()
        try:
            self.update_info(get('https://www.wcyt.org/api/track', params=params).json())
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'An error occured trying to send the request: {e}', QMessageBox.Ok)
            self.found_label.setText('Error')
        QApplication.restoreOverrideCursor()
        self.search_button.setDisabled(False)

    def update_info(self, info):
        if 'message' in info and info['message'] != 'Track not found':
            return QMessageBox.critical(self, 'Error', f'LastFM returned an error: ({ info["error"] }) { info["message"] }')
        if 'message' in info and info['message'] == 'Track not found':
            self.album.scene().clear()
            self.found_label.setText('Track not found')
            self.info_detail.hide()
            self.info.show()
            return

        track = info['track']

        duration = int(track['duration']) / 1000
        minutes, seconds = divmod(duration, 60)
        minutes = int(minutes)
        seconds = '{:0>2}'.format(int(seconds)) if seconds == int(seconds) else '{:05.2f}'.format(seconds)
        self.name_label.setText(f'<a href="{ track["url"] }">{ track["name"] }</a>')
        self.duration_label.setText(f'{ minutes }:{ seconds }')
        self.artist_label.setText(f'<a href="{ track["artist"]["url"] }">{ track["artist"]["name"] }</a>')

        self.album_label.setText(f'<a href="{ track["album"]["url"] }">{ track["album"]["title"] }</a>' if 'album' in track else 'Album not found')

        if 'album' in track and 'image' in track['album'] and track['album']['image'][-1]['#text']:
            image = track['album']['image'][-1]['#text']
            self.image_label.setText(f'<a href="{ image }">{ image }</a>')
            pixmap = QPixmap()
            pixmap.loadFromData(get(image).content)
            self.album.scene().addPixmap(pixmap)
        else:
            self.album.scene().clear()
            self.image_label.setText('Image not found')

        self.found_label.setText('Found Track')
        self.info_detail.show()
        self.info.show()
    
    def show_settings(self):
        self.settings.show()

    def get_clipboard_text(self):
        user32.OpenClipboard(0)
        try:
            if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                data = user32.GetClipboardData(CF_UNICODETEXT)
                data_locked = kernel32.GlobalLock(data)
                text = ctypes.c_wchar_p(data_locked)
                value = text.value
                kernel32.GlobalUnlock(data_locked)
                return value
        finally:
            user32.CloseClipboard()
    
    def query_clipboard_changes(self):
        if self.isActiveWindow(): return
        if not self.settings.monitor_clipboard: return
        text = self.get_clipboard_text()
        if type(text) != str: return
        if self.last_text == text: return

        search_result = search(r'([\S ]+)(?:\s*(-)\s*|[^ \S]+)([\S ]+)', text)

        if (search_result):
            [track, artist] = map(search_result.group, [3, 1] if search_result.group(2) else [1, 3])
            self.track.setText(track)
            self.artist.setText(artist)
            if (self.settings.auto_search):
                self.search()

        self.last_text = text


if __name__ == '__main__':
    appctxt = ApplicationContext()
    window = MainWindow()
    sys.exit(appctxt.app.exec_())