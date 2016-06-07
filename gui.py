import sys
import os
import tracking as tt
import numpy as np
import pdb
import cv2
import json
import threading

from matplotlib.backends import qt_compat
use_pyside = qt_compat.QT_API == qt_compat.QT_API_PYSIDE
if use_pyside:
    from PySide import QtGui, QtCore
else:
    from PyQt4 import QtGui, QtCore

from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.axes import Axes
import matplotlib.pyplot as plt

gray_color_table = [QtGui.qRgb(i, i, i) for i in range(256)]

default_params = {'shrink_factor': 1.0,
                  'offset': None,
                  'crop': None,
                  'tail_threshold': 200,
                  'head_threshold': 50,
                  'invert': False,
                  'video_opened': False,
                  'folder_opened': False,
                  'image_opened': False,
                  'min_eye_distance': 20,
                  'eye_1_index': 0,
                  'eye_2_index': 1,
                  'track_head_bool': True,
                  'track_tail_bool': True,
                  'show_head_threshold': False,
                  'show_tail_threshold': False,
                  'last_path': "",
                 }

class PlotQLabel(QtGui.QLabel):
    def mousePressEvent(self, event):
        self.y_start = int(event.y()/self.scale_factor)
        self.x_start = int(event.x()/self.scale_factor)

    def mouseMoveEvent(self, event):
        self.y_end = int(event.y()/self.scale_factor)
        self.x_end = int(event.x()/self.scale_factor)

        self.plot_window.draw_crop_selection(self.y_start, self.y_end, self.x_start, self.x_end)

    def mouseReleaseEvent(self, event):
        self.y_end = int(event.y()/self.scale_factor)
        self.x_end = int(event.x()/self.scale_factor)

        self.plot_window.crop_selection(self.y_start, self.y_end, self.x_start, self.x_end)

    def set_plot_window(self, plot_window):
        self.plot_window = plot_window

    def set_scale_factor(self, scale_factor):
        self.scale_factor = scale_factor

class PlotWindow(QtGui.QMainWindow):
    def __init__(self, param_window):
        QtGui.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("Preview")

        self.param_window = param_window

        self.param_window.imageLoaded.connect(self.plot_image)
        self.param_window.imageTracked.connect(self.plot_tracked_image)
        self.param_window.thresholdLoaded.connect(self.plot_threshold_image)
        self.param_window.thresholdUnloaded.connect(self.remove_threshold_image)

        self.main_widget = QtGui.QWidget(self)
        self.main_widget.setStyleSheet("background-color:#555555;")

        self.l = QtGui.QVBoxLayout(self.main_widget)
        self.l1 = PlotQLabel()
        self.l1.setSizePolicy(QtGui.QSizePolicy.MinimumExpanding, QtGui.QSizePolicy.MinimumExpanding)
        self.l1.setAcceptDrops(True)
        self.l1.set_plot_window(self)
        self.l1.setAlignment(QtCore.Qt.AlignCenter)
        self.l.setAlignment(QtCore.Qt.AlignCenter)
        self.l.addWidget(self.l1)

        self.image_slider = None

        self.orig_image    = None
        self.tracking_list = None
        self.orig_pix      = None
        self.pix_size      = None

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

    def resizeEvent(self, event):
        QtGui.QMainWindow.resizeEvent(self, event)

        width = self.main_widget.width() - 40
        height = self.main_widget.height() - 40

        self.pix_size = min(max(min(width, height), 400), 900)

        if self.orig_pix:
            scale_factor = float(self.pix_size)/max(self.orig_pix.width(), self.orig_pix.height())
            self.l1.set_scale_factor(float(self.pix_size)/max(self.orig_pix.width(), self.orig_pix.height()))
            pix = self.orig_pix.scaled(self.pix_size, self.pix_size, QtCore.Qt.KeepAspectRatio)
            self.l1.setPixmap(pix)
            self.l1.setFixedSize(pix.size())

    def plot_threshold_image(self, threshold_image, new_image=False):
        new_threshold_image = threshold_image * 255

        self.orig_image = new_threshold_image

        if new_image:
            self.tracking_list = None

        if self.tracking_list:
            self.plot_tracked_image(new_threshold_image, self.tracking_list)
        else:
            rgb_image = np.repeat(new_threshold_image[:, :, np.newaxis], 3, axis=2)

            height, width, bytesPerComponent = rgb_image.shape
            bytesPerLine = bytesPerComponent * width
            cv2.cvtColor(rgb_image, cv2.COLOR_BGR2RGB, rgb_image)

            qimage = QtGui.QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0], bytesPerLine, QtGui.QImage.Format_RGB888)
            qimage.setColorTable(gray_color_table)

            self.orig_pix = QtGui.QPixmap(qimage)

            self.l1.set_scale_factor(float(self.pix_size)/max(self.orig_pix.width(), self.orig_pix.height()))

            pix = self.orig_pix.scaled(self.pix_size, self.pix_size, QtCore.Qt.KeepAspectRatio)
            self.l1.setPixmap(pix)
            self.l1.setFixedSize(pix.size())

    def remove_threshold_image(self, image):
        self.orig_image = np.copy(image)
        self.plot_image(self.orig_image)

    def plot_image(self, image, new_image=False):
        if not self.param_window.image_opened:
            if self.image_slider:
                self.image_slider.setMaximum(self.param_window.n_frames-1)
            else:
                # create image slider
                self.image_slider = QtGui.QSlider(QtCore.Qt.Horizontal)
                self.image_slider.setFocusPolicy(QtCore.Qt.StrongFocus)
                self.image_slider.setTickPosition(QtGui.QSlider.TicksBothSides)
                self.image_slider.setTickInterval(1)
                self.image_slider.setSingleStep(1)
                self.image_slider.setMinimum(0)
                self.image_slider.setMaximum(self.param_window.n_frames-1)
                self.image_slider.setValue(0)
                self.image_slider.valueChanged.connect(self.switch_image)

                self.l.addWidget(self.image_slider)

        if new_image:
            self.tracking_list = None

        self.orig_image = np.copy(image)

        if self.tracking_list:
            self.plot_tracked_image(image, self.tracking_list)
        else:
            rgb_image = np.repeat(image[:, :, np.newaxis], 3, axis=2)

            height, width, bytesPerComponent = rgb_image.shape
            bytesPerLine = bytesPerComponent * width
            cv2.cvtColor(rgb_image, cv2.COLOR_BGR2RGB, rgb_image)

            qimage = QtGui.QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0], bytesPerLine, QtGui.QImage.Format_RGB888)
            qimage.setColorTable(gray_color_table)

            self.orig_pix = QtGui.QPixmap(qimage)

            self.l1.set_scale_factor(float(self.pix_size)/max(self.orig_pix.width(), self.orig_pix.height()))

            pix = self.orig_pix.scaled(self.pix_size, self.pix_size, QtCore.Qt.KeepAspectRatio)
            self.l1.setPixmap(pix)
            self.l1.setFixedSize(pix.size())

    def switch_image(self, value):
        self.param_window.switch_image(value)

    def plot_tracked_image(self, image, tracking_list):
        self.tracking_list = tracking_list

        tail_y_coords   = self.tracking_list[0]
        tail_x_coords   = self.tracking_list[1]
        spline_y_coords = self.tracking_list[2]
        spline_x_coords = self.tracking_list[3]
        eye_y_coords    = self.tracking_list[4]
        eye_x_coords    = self.tracking_list[5]
        perp_y_coords   = self.tracking_list[6]
        perp_x_coords   = self.tracking_list[7]

        image = tt.plot_image(image, tail_y_coords, tail_x_coords, spline_y_coords, spline_x_coords,
                                eye_y_coords, eye_x_coords, perp_y_coords, perp_x_coords)

        self.orig_image = np.copy(image)

        height, width, bytesPerComponent = image.shape
        bytesPerLine = bytesPerComponent * width
        cv2.cvtColor(image, cv2.COLOR_BGR2RGB, image)

        qimage = QtGui.QImage(image.data, image.shape[1], image.shape[0], bytesPerLine, QtGui.QImage.Format_RGB888)
        qimage.setColorTable(gray_color_table)

        self.orig_pix = QtGui.QPixmap(qimage)

        self.l1.set_scale_factor(float(self.pix_size)/max(self.orig_pix.width(), self.orig_pix.height()))

        pix = self.orig_pix.scaled(self.pix_size, self.pix_size, QtCore.Qt.KeepAspectRatio)
        self.l1.setPixmap(pix)
        self.l1.setFixedSize(pix.size())

    def draw_crop_selection(self, y_start, y_end, x_start, x_end):
        image = np.copy(self.orig_image)

        if len(image.shape) < 3:
            rgb_image = np.repeat(image[:, :, np.newaxis], 3, axis=2)
        else:
            rgb_image = image

        overlay = rgb_image.copy()

        cv2.rectangle(overlay, (x_start, y_start), (x_end, y_end), (0, 51, 255), -1)

        cv2.addWeighted(overlay, 0.5, rgb_image, 0.5, 0, rgb_image)

        height, width, bytesPerComponent = rgb_image.shape
        bytesPerLine = bytesPerComponent * width
        cv2.cvtColor(rgb_image, cv2.COLOR_BGR2RGB, rgb_image)

        qimage = QtGui.QImage(rgb_image.data, rgb_image.shape[1], rgb_image.shape[0], bytesPerLine, QtGui.QImage.Format_RGB888)
        qimage.setColorTable(gray_color_table)

        self.orig_pix = QtGui.QPixmap(qimage)

        pix = self.orig_pix.scaled(self.pix_size, self.pix_size, QtCore.Qt.KeepAspectRatio)
        self.l1.setPixmap(pix)
        self.l1.setFixedSize(pix.size())


    def crop_selection(self, y_start, y_end, x_start, x_end):
        self.param_window.update_crop_from_selection(y_start, y_end, x_start, x_end)

    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        self.fileQuit()

class ParamWindow(QtGui.QMainWindow):
    imageLoaded       = QtCore.pyqtSignal(np.ndarray, bool)
    imageTracked      = QtCore.pyqtSignal(np.ndarray, list)
    thresholdLoaded   = QtCore.pyqtSignal(np.ndarray, bool)
    thresholdUnloaded = QtCore.pyqtSignal(np.ndarray)

    def __init__(self):
        QtGui.QMainWindow.__init__(self)

        self.plot_window = PlotWindow(self)
        self.plot_window.setWindowTitle("Preview")
        self.plot_window.show()

        self.head_threshold_image = None
        self.tail_threshold_image = None
        self.image = None

        self.setGeometry(100, 200, 300, 800)

        openFolder = QtGui.QAction(QtGui.QIcon('open.png'), 'Open Directory', self)
        openFolder.setShortcut('Ctrl+Shift+O')
        openFolder.setStatusTip('Open a directory of images')
        openFolder.triggered.connect(lambda:self.open_folder(""))

        openVideo = QtGui.QAction(QtGui.QIcon('open.png'), 'Open Video', self)
        openVideo.setShortcut('Ctrl+Alt+O')
        openVideo.setStatusTip('Open a video')
        openVideo.triggered.connect(lambda:self.open_video(""))

        openImage = QtGui.QAction(QtGui.QIcon('open.png'), 'Open Image', self)
        openImage.setShortcut('Ctrl+O')
        openImage.setStatusTip('Open a video')
        openImage.triggered.connect(lambda:self.open_image(""))

        trackFrame = QtGui.QAction(QtGui.QIcon('open.png'), 'Track Frame', self)
        trackFrame.setShortcut('Ctrl+T')
        trackFrame.setStatusTip('Track current image')
        trackFrame.triggered.connect(self.track_frame)

        saveParams = QtGui.QAction(QtGui.QIcon('save.png'), 'Save parameters', self)
        saveParams.setShortcut('Return')
        saveParams.setStatusTip('Save parameters')
        saveParams.triggered.connect(self.save_params)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(openFolder)
        fileMenu.addAction(openVideo)
        fileMenu.addAction(openImage)
        fileMenu.addAction(saveParams)
        fileMenu.addAction(trackFrame)

        self.mainWidget = QtGui.QWidget(self)
        self.setCentralWidget(self.mainWidget)

        self.layout = QtGui.QVBoxLayout()
        self.form_layout = QtGui.QFormLayout()

        self.load_params()

        self.param_controls = {}

        self.add_checkbox('invert', "Invert image", self.toggle_invert_image, self.invert)
        self.add_checkbox('show_head_threshold', "Show head threshold", self.toggle_threshold_image, self.show_head_threshold)
        self.add_checkbox('show_tail_threshold', "Show tail threshold", self.toggle_threshold_image, self.show_tail_threshold)
        self.add_checkbox('track_head_bool', "Track head", self.toggle_tracking, self.track_head_bool)
        self.add_checkbox('track_tail_bool', "Track tail", self.toggle_tracking, self.track_tail_bool)

        self.open_last_file()

        if self.crop == None:
            self.add_slider('crop_y', 'Crop y:', 1, 100, 100)
            self.add_slider('crop_x', 'Crop x:', 1, 100, 100)
        else:
            self.add_slider('crop_y', 'Crop y:', 1, 500, round(500.0*self.crop[0]/self.image.shape[0]))
            self.add_slider('crop_x', 'Crop x:', 1, 500, round(500.0*self.crop[1]/self.image.shape[1]))

        if self.offset == None:
            self.add_slider('offset_y', 'Offset y:', 0, 499, 0)
            self.add_slider('offset_x', 'Offset x:', 0, 499, 0)
        else:
            self.add_slider('offset_y', 'Offset y:', 0, 499, round(500.0*self.offset[0]/self.image.shape[0]))
            self.add_slider('offset_x', 'Offset x:', 0, 499, round(500.0*self.offset[1]/self.image.shape[1]))

        self.add_slider('shrink_factor', 'Shrink factor:', 1, 10, int(10*self.shrink_factor))
        self.add_slider('eye_1_index', 'Index of eye 1:', 0, 5, self.eye_1_index)
        self.add_slider('eye_2_index', 'Index of eye 2:', 0, 5, self.eye_2_index)
        self.add_textbox('min_eye_distance', 'Minimum distance b/w eye & tail:', self.min_eye_distance)
        self.add_textbox('head_threshold', 'Head threshold:', self.head_threshold)
        self.add_textbox('tail_threshold', 'Tail threshold:', self.tail_threshold)

        self.layout.addLayout(self.form_layout)

        hbox1 = QtGui.QHBoxLayout()
        hbox1.addStretch(1)
        hbox2 = QtGui.QHBoxLayout()
        hbox2.addStretch(1)

        self.open_image_button = QtGui.QPushButton('Open Image', self)
        self.open_image_button.setMinimumHeight(10)
        self.open_image_button.setMaximumWidth(180)
        self.open_image_button.clicked.connect(lambda:self.open_image(""))
        hbox1.addWidget(self.open_image_button)

        self.open_folder_button = QtGui.QPushButton('Open Folder', self)
        self.open_folder_button.setMinimumHeight(10)
        self.open_folder_button.setMaximumWidth(180)
        self.open_folder_button.clicked.connect(lambda:self.open_folder(""))
        hbox1.addWidget(self.open_folder_button)

        self.open_video_button = QtGui.QPushButton('Open Video', self)
        self.open_video_button.setMinimumHeight(10)
        self.open_video_button.setMaximumWidth(180)
        self.open_video_button.clicked.connect(lambda:self.open_video(""))
        hbox1.addWidget(self.open_video_button)

        self.save_button = QtGui.QPushButton('Save', self)
        self.save_button.setMinimumHeight(10)
        self.save_button.setMaximumWidth(80)
        self.save_button.clicked.connect(self.save_params)
        hbox1.addWidget(self.save_button)

        self.track_button = QtGui.QPushButton('Track', self)
        self.track_button.setMinimumHeight(10)
        self.track_button.setMaximumWidth(80)
        self.track_button.clicked.connect(self.track_frame)
        hbox2.addWidget(self.track_button)

        self.track_button = QtGui.QPushButton('Track and Save', self)
        self.track_button.setMinimumHeight(10)
        self.track_button.setMaximumWidth(180)
        self.track_button.clicked.connect(self.track)
        hbox2.addWidget(self.track_button)

        self.reset_crop_button = QtGui.QPushButton('Reset Crop', self)
        self.reset_crop_button.setMinimumHeight(10)
        self.reset_crop_button.setMaximumWidth(180)
        self.reset_crop_button.clicked.connect(self.reset_crop)
        hbox2.addWidget(self.reset_crop_button)

        self.layout.addLayout(hbox1)
        self.layout.addLayout(hbox2)

        self.layout.setAlignment(QtCore.Qt.AlignTop)

        self.mainWidget.setLayout(self.layout)

        self.setWindowTitle('File dialog')
        self.show()

        if self.image is not None:
            self.reshape_image()

    def load_params(self):
        # sete xperiments file
        self.params_file = "last_params.json"

        try:
            # load experiments
            with open(self.params_file, "r") as input_file:
                self.params = json.load(input_file)
        except:
            # if none exist, create & save a default experiment
            self.params = default_params
            self.save_params_file()

        if self.params['last_path'] == "":
            self.params = default_params

        self.shrink_factor       = self.params['shrink_factor']
        self.offset              = self.params['offset']
        self.crop                = self.params['crop']
        self.tail_threshold      = self.params['tail_threshold']
        self.head_threshold      = self.params['head_threshold']
        self.invert              = self.params['invert']
        self.min_eye_distance    = self.params['min_eye_distance']
        self.eye_1_index         = self.params['eye_1_index']
        self.eye_2_index         = self.params['eye_2_index']
        self.track_head_bool     = self.params['track_head_bool']
        self.track_tail_bool     = self.params['track_tail_bool']
        self.show_head_threshold = self.params['show_head_threshold']
        self.show_tail_threshold = self.params['show_tail_threshold']
        self.video_opened        = self.params['video_opened']
        self.folder_opened       = self.params['folder_opened']
        self.image_opened        = self.params['image_opened']

    def open_last_file(self):
        try:
            if self.video_opened == True:
                self.open_video(path=self.params['last_path'])
            elif self.folder_opened == True:
                self.open_folder(path=self.params['last_path'])
            elif self.image_opened == True:
                self.open_image(path=self.params['last_path'])
        except:
            pass

    def save_params_file(self):
        # save experiments to file
        with open(self.params_file, "w") as output_file:
            json.dump(self.params, output_file)

    def add_textbox(self, label, description, default_value):
        param_box = QtGui.QLineEdit(self)
        param_box.setMinimumHeight(10)
        self.form_layout.addRow(description, param_box)
        if default_value != None:
            param_box.setText(str(default_value))

        self.param_controls[label] = param_box

    def add_slider(self, label, description, minimum, maximum, value, tick_interval=2, single_step=0.5):
        slider = QtGui.QSlider(QtCore.Qt.Horizontal)
        slider.setFocusPolicy(QtCore.Qt.StrongFocus)
        slider.setTickPosition(QtGui.QSlider.TicksBothSides)
        slider.setTickInterval(tick_interval)
        slider.setSingleStep(single_step)
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setValue(value)
        slider.setMinimumWidth(200)

        slider.valueChanged.connect(self.save_params)
        self.form_layout.addRow(description, slider)
        self.param_controls[label] = slider

    def add_checkbox(self, label, description, toggle_func, checked):
        checkbox = QtGui.QCheckBox(description)
        checkbox.setChecked(checked)

        checkbox.toggled.connect(lambda:toggle_func(checkbox))
        self.layout.addWidget(checkbox)
        self.param_controls[label] = checkbox

    def open_folder(self, path=""):
        if path == "":
            self.path = str(QtGui.QFileDialog.getExistingDirectory(self, 'Open folder'))
        else:
            self.path = path

        if self.path != "":
            self.n_frames = 0
            self.image_paths = []

            for filename in sorted(os.listdir(self.path)):
                if filename.endswith('.tif') or filename.endswith('.png'):
                    image_path = self.path + "/" + filename
                    self.image_paths.append(image_path)
                    self.n_frames += 1

            if self.n_frames == 0:
                print("Could not find any images.")
                return

            if len(self.image_paths) >= 100:
                f = lambda m, n: [i*n//m + n//(2*m) for i in range(m)]
                self.image_paths = [ self.image_paths[i] for i in f(100, self.n_frames)]
                self.n_frames = 100

            self.folder_opened = True
            self.video_opened  = False
            self.image_opened  = False

            self.switch_image(0)

    def open_image(self, path=""):
        if path == "":
            self.path = str(QtGui.QFileDialog.getOpenFileName(self, 'Open image', '', 'Images (*.jpg *.tif *.png)'))
        else:
            self.path = path

        if self.path != "":
            self.n_frames = 1

            self.folder_opened = False
            self.video_opened  = False
            self.image_opened  = True

            self.switch_image(0)

    def open_video(self, path=""):
        if path == "":
            self.path = str(QtGui.QFileDialog.getOpenFileName(self, 'Open video', '', 'Videos (*.mov *.tif *.mp4 *.avi)'))
        else:
            self.path = path

        if self.path != "":
            self.frames = tt.load_video(self.path, n_frames=100)

            if self.frames != None:
                self.n_frames = len(self.frames)

                self.folder_opened = False
                self.video_opened  = True
                self.image_opened  = False

                self.switch_image(0)

    def switch_image(self, n):
        if self.video_opened:
            print("Switching to frame {}".format(n))
            self.image = self.frames[n]
        elif self.folder_opened:
            self.image = tt.load_image(self.image_paths[n])
        elif self.image_opened:
            self.image = tt.load_image(self.path)

        if self.crop == None or self.offset == None:
            self.crop = self.image.shape
            self.param_controls['crop_y'].setValue(500*self.image.shape[0])
            self.param_controls['crop_x'].setValue(500*self.image.shape[1])

            self.offset = (0, 0)
            self.param_controls['offset_y'].setValue(0)
            self.param_controls['offset_x'].setValue(0)

        if self.param_controls['invert'].isChecked():
            self.invert_image()
        self.reshape_image(new_image=True)

    def reshape_image(self, new_image=False):
        # shrink the image
        if self.shrink_factor != None:
            self.shrunken_image = tt.shrink_image(self.image, self.shrink_factor)

        # crop the image
        if self.crop is not None and self.offset is not None:
            print(self.crop, self.offset, self.shrink_factor, self.image.shape)
            crop = (round(self.crop[0]*self.shrink_factor), round(self.crop[1]*self.shrink_factor))
            offset = (round(self.offset[0]*self.shrink_factor), round(self.offset[1]*self.shrink_factor))

            self.cropped_image = tt.crop_image(self.shrunken_image, offset, crop)

        self.threshold_image()

        self.update_plot(new_image=new_image)

    def threshold_image(self):
        self.head_threshold_image = tt.get_head_threshold_image(self.cropped_image, self.head_threshold)
        self.tail_threshold_image = tt.get_tail_threshold_image(self.cropped_image, self.tail_threshold)

    def update_plot(self, new_image=False):
        if not self.signalsBlocked():
            if self.param_controls["show_head_threshold"].isChecked():
                self.thresholdLoaded.emit(self.head_threshold_image, new_image)
            elif self.param_controls["show_tail_threshold"].isChecked():
                self.thresholdLoaded.emit(self.tail_threshold_image, new_image)
            else:
                self.imageLoaded.emit(self.cropped_image, new_image)

    def invert_image(self):
        self.image = (255 - self.image)

    def toggle_invert_image(self, checkbox):
        if checkbox.isChecked():
            self.invert = True
        else:
            self.invert = False
        self.invert_image()
        self.reshape_image()

    def toggle_threshold_image(self, checkbox):
        if self.head_threshold_image != None:
            if checkbox.isChecked():
                if not self.signalsBlocked():
                    if checkbox.text() == "Show head threshold":
                        self.param_controls["show_tail_threshold"].setChecked(False)
                        self.thresholdLoaded.emit(self.head_threshold_image, False)
                    elif checkbox.text() == "Show tail threshold":
                        self.param_controls["show_head_threshold"].setChecked(False)
                        self.thresholdLoaded.emit(self.tail_threshold_image, False)
            else:
                if not self.signalsBlocked():
                    self.thresholdUnloaded.emit(self.cropped_image)

    def toggle_tracking(self, checkbox):
        if checkbox.isChecked():
            track = True
        else:
            track = False

        if checkbox.text() == "Track head":
            self.track_head_bool = track
        elif checkbox.text() == "Track tail":
            self.track_tail_bool = track

    def save_params(self):
        print("Saving params.")
        crop_y = self.param_controls['crop_y'].value()*self.image.shape[0]/500
        crop_x = self.param_controls['crop_x'].value()*self.image.shape[1]/500
        offset_y = self.param_controls['offset_y'].value()*self.image.shape[0]/500
        offset_x = self.param_controls['offset_x'].value()*self.image.shape[1]/500

        self.eye_1_index = int(self.param_controls['eye_1_index'].value())
        self.eye_2_index = int(self.param_controls['eye_2_index'].value())
        self.min_eye_distance = int(self.param_controls['min_eye_distance'].text())

        new_head_threshold = int(self.param_controls['head_threshold'].text())
        new_tail_threshold = int(self.param_controls['tail_threshold'].text())
        new_crop = (int(crop_y), int(crop_x))
        new_offset = (int(offset_y), int(offset_x))
        new_shrink_factor = float(self.param_controls['shrink_factor'].value())/10.0

        generate_new_image = False

        if self.crop != new_crop:
            self.crop = new_crop
            generate_new_image = True
        if self.offset != new_offset:
            self.offset = new_offset
            generate_new_image = True
        if self.shrink_factor != new_shrink_factor:
            self.shrink_factor = new_shrink_factor
            generate_new_image = True
        if self.head_threshold != new_head_threshold:
            self.head_threshold = new_head_threshold
            generate_new_image = True
        if self.tail_threshold != new_tail_threshold:
            self.tail_threshold = new_tail_threshold
            generate_new_image = True

        self.params['shrink_factor']       = self.shrink_factor
        self.params['offset']              = self.offset
        self.params['crop']                = self.crop
        self.params['tail_threshold']      = self.tail_threshold
        self.params['head_threshold']      = self.head_threshold
        self.params['min_eye_distance']    = self.min_eye_distance
        self.params['eye_1_index']         = self.eye_1_index
        self.params['eye_2_index']         = self.eye_2_index
        self.params['track_head_bool']     = self.track_head_bool
        self.params['track_tail_bool']     = self.track_tail_bool
        self.params['show_head_threshold'] = self.show_head_threshold
        self.params['show_tail_threshold'] = self.show_tail_threshold
        self.params['video_opened']        = self.video_opened
        self.params['folder_opened']       = self.folder_opened
        self.params['image_opened']        = self.image_opened
        self.params['invert']              = self.invert
        self.params['last_path']           = self.path

        self.save_params_file()

        if generate_new_image:
            self.reshape_image(new_image=True)

    def track_frame(self):
        self.save_params()

        if self.track_head_bool:
            (eye_y_coords, eye_x_coords,
            perp_y_coords, perp_x_coords) = tt.track_head(self.head_threshold_image,
                                                            self.eye_1_index, self.eye_2_index)

            if eye_x_coords == None:
                print("Could not track head.")
        else:
            (eye_y_coords, eye_x_coords,
            perp_y_coords, perp_x_coords) = [None]*4

        if self.track_tail_bool:
            (tail_y_coords, tail_x_coords,
            spline_y_coords, spline_x_coords) = tt.track_tail(self.tail_threshold_image,
                                                                eye_x_coords, eye_y_coords,
                                                                min_eye_distance=self.min_eye_distance*self.shrink_factor)
            if tail_x_coords == None:
                print("Could not track tail.")
        else:
            (tail_y_coords, tail_x_coords,
            spline_y_coords, spline_x_coords) = [None]*4

        if not self.signalsBlocked():
            if self.param_controls["show_head_threshold"].isChecked():
                self.imageTracked.emit(self.head_threshold_image*255, [tail_y_coords, tail_x_coords,
                    spline_y_coords, spline_x_coords,
                    eye_y_coords,
                    eye_x_coords,
                    perp_y_coords,
                    perp_x_coords])
            elif self.param_controls["show_tail_threshold"].isChecked():
                self.imageTracked.emit(self.tail_threshold_image*255, [tail_y_coords, tail_x_coords,
                    spline_y_coords, spline_x_coords,
                    eye_y_coords,
                    eye_x_coords,
                    perp_y_coords,
                    perp_x_coords])
            else:
                self.imageTracked.emit(self.cropped_image, [tail_y_coords, tail_x_coords,
                    spline_y_coords, spline_x_coords,
                    eye_y_coords,
                    eye_x_coords,
                    perp_y_coords,
                    perp_x_coords])

    def track(self):
        if self.image_opened:
            self.track_image()
        elif self.folder_opened:
            self.track_folder()
        elif self.video_opened:
            self.track_video()

    def track_image(self):
        self.save_path = str(QtGui.QFileDialog.getSaveFileName(self, 'Save image', '', 'Images (*.jpg *.tif *.png)'))

        kwargs_dict = { 'crop': self.crop,
                        'offset': self.offset,
                        'shrink_factor': self.shrink_factor,
                        'invert': self.invert,
                        'min_eye_distance': self.min_eye_distance,
                        'eye_1_index': self.eye_1_index,
                        'eye_2_index': self.eye_2_index,
                        'head_threshold': self.head_threshold,
                        'tail_threshold': self.tail_threshold,
                        'track_head_bool': self.track_head_bool,
                        'track_tail_bool': self.track_tail_bool
                      }

        t = threading.Thread(target=tt.track_image, args=(self.path, self.save_path), kwargs=kwargs_dict)

        t.start()

    def track_folder(self):
        self.save_path = str(QtGui.QFileDialog.getSaveFileName(self, 'Save video', '', 'Videos (*.mov *.tif *.mp4 *.avi)'))

        kwargs_dict = { 'crop': self.crop,
                        'offset': self.offset,
                        'shrink_factor': self.shrink_factor,
                        'invert': self.invert,
                        'min_eye_distance': self.min_eye_distance,
                        'eye_1_index': self.eye_1_index,
                        'eye_2_index': self.eye_2_index,
                        'head_threshold': self.head_threshold,
                        'tail_threshold': self.tail_threshold,
                        'track_head_bool': self.track_head_bool,
                        'track_tail_bool': self.track_tail_bool
                      }

        t = threading.Thread(target=tt.track_folder, args=(self.path, self.save_path), kwargs=kwargs_dict)

        t.start()

    def track_video(self):
        print("Invert:", self.invert)
        self.save_path = str(QtGui.QFileDialog.getSaveFileName(self, 'Save video', '', 'Videos (*.mov *.tif *.mp4 *.avi)'))

        kwargs_dict = { 'crop': self.crop,
                        'offset': self.offset,
                        'shrink_factor': self.shrink_factor,
                        'invert': self.invert,
                        'min_eye_distance': self.min_eye_distance,
                        'eye_1_index': self.eye_1_index,
                        'eye_2_index': self.eye_2_index,
                        'head_threshold': self.head_threshold,
                        'tail_threshold': self.tail_threshold,
                        'track_head_bool': self.track_head_bool,
                        'track_tail_bool': self.track_tail_bool
                      }

        t = threading.Thread(target=tt.track_video, args=(self.path, self.save_path), kwargs=kwargs_dict)

        t.start()

    def update_crop_from_selection(self, y_start, y_end, x_start, x_end):
        if abs(y_end - y_start) != 0 and abs(x_end - x_start) != 0:
            y_start = round(y_start/self.shrink_factor)
            y_end   = round(y_end/self.shrink_factor)
            x_start = round(x_start/self.shrink_factor)
            x_end   = round(x_end/self.shrink_factor)
            end_add = round(1*self.shrink_factor)

            self.crop = (abs(y_end - y_start)+end_add, abs(x_end - x_start)+end_add)
            self.offset = (self.offset[0] + min(y_start, y_end), self.offset[1] + min(x_start, x_end))

            self.param_controls['crop_y'].blockSignals(True)
            self.param_controls['crop_x'].blockSignals(True)
            self.param_controls['offset_y'].blockSignals(True)
            self.param_controls['offset_x'].blockSignals(True)

            self.param_controls['crop_y'].setValue(round(500.0*self.crop[0]/self.image.shape[0]))
            self.param_controls['crop_x'].setValue(round(500.0*self.crop[1]/self.image.shape[1]))

            self.param_controls['offset_y'].setValue(round(500.0*self.offset[0]/self.image.shape[0]))
            self.param_controls['offset_x'].setValue(round(500.0*self.offset[1]/self.image.shape[1]))

            self.param_controls['crop_y'].blockSignals(False)
            self.param_controls['crop_x'].blockSignals(False)
            self.param_controls['offset_y'].blockSignals(False)
            self.param_controls['offset_x'].blockSignals(False)

            self.reshape_image(new_image=True)

    def reset_crop(self):
        self.crop = (self.image.shape[0], self.image.shape[1])
        self.offset = (0, 0)

        self.param_controls['crop_y'].blockSignals(True)
        self.param_controls['crop_x'].blockSignals(True)
        self.param_controls['offset_y'].blockSignals(True)
        self.param_controls['offset_x'].blockSignals(True)

        self.param_controls['crop_y'].setValue(round(500.0*self.crop[0]/self.image.shape[0]))
        self.param_controls['crop_x'].setValue(round(500.0*self.crop[1]/self.image.shape[1]))

        self.param_controls['offset_y'].setValue(round(500.0*self.offset[0]/self.image.shape[0]))
        self.param_controls['offset_x'].setValue(round(500.0*self.offset[1]/self.image.shape[1]))

        self.param_controls['crop_y'].blockSignals(False)
        self.param_controls['crop_x'].blockSignals(False)
        self.param_controls['offset_y'].blockSignals(False)
        self.param_controls['offset_x'].blockSignals(False)

        self.reshape_image(new_image=True)

    def fileQuit(self):
        self.close()

    def closeEvent(self, ce):
        self.fileQuit()

qApp = QtGui.QApplication(sys.argv)
# qApp.setStyle("cleanlooks")

param_window = ParamWindow()
param_window.setWindowTitle("Parameters")
param_window.show()

sys.exit(qApp.exec_())