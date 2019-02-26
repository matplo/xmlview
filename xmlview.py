#!/usr/bin/env python

import os
import sys
import argparse
import Tkinter as tk
import ttk
import tkMessageBox
from idlelib.WidgetRedirector import WidgetRedirector
import datetime
import subprocess
import platform

import logging
global logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
logFormatterInfoSteam = logging.Formatter("%(asctime)s [%(levelname)-7.7s] %(message)s")
consoleHandler.setFormatter(logFormatterInfoSteam)
logger.addHandler(consoleHandler)

global args

try:
	from lxml import etree
	logger.debug("running with lxml.etree")
except ImportError:
	try:
		# Python 2.5
		import xml.etree.cElementTree as etree
		logger.debug("running with cElementTree on Python 2.5+")
	except ImportError:
		try:
			# Python 2.5
			import xml.etree.ElementTree as etree
			logger.debug("running with ElementTree on Python 2.5+")
		except ImportError:
			try:
				# normal cElementTree install
				import cElementTree as etree
				logger.debug("running with cElementTree")
			except ImportError:
				try:
					# normal ElementTree install
					import elementtree.ElementTree as etree
					logger.debug("running with ElementTree")
				except ImportError:
					logger.error("Failed to import ElementTree from any known place")


class HyperlinkManager:
	def __init__(self, text):
		self.text = text
		self.text.tag_config("hyper", foreground="blue", underline=1)
		self.text.tag_bind("hyper", "<Enter>", self._enter)
		self.text.tag_bind("hyper", "<Leave>", self._leave)
		self.text.tag_bind("hyper", "<Button-1>", self._click)
		self.reset()

	def reset(self):
		self.links = {}
		self.args = {}

	def add(self, action, arg):
		# add an action to the manager.  returns tags to use in
		# associated text widget
		tag = "hyper-%d" % len(self.links)
		self.links[tag] = action
		self.args[tag] = arg
		return "hyper", tag, arg

	def _enter(self, event):
		self.text.config(cursor="hand2")

	def _leave(self, event):
		self.text.config(cursor="")

	def _click(self, event):
		for tag in self.text.tag_names(CURRENT):
			if tag[:6] == "hyper-":
				self.links[tag](self.args[tag])
				return


class XMLTagManager:
	def __init__(self, text):
		self.text = text
		self.text.tag_config("xmltag", foreground="black", background="yellow", underline=1)
		self.text.tag_bind("xmltag", "<Enter>", self._enter)
		self.text.tag_bind("xmltag", "<Leave>", self._leave)
		self.text.tag_bind("xmltag", "<Button-1>", self._click)
		self.reset()

	def reset(self):
		self.links = {}
		self.args = {}

	def add(self, action, arg):
		# add an action to the manager.  returns tags to use in
		# associated text widget
		tag = "xmltag-%d" % len(self.links)
		self.links[tag] = action
		self.args[tag] = arg
		return "xmltag", tag, arg

	def _enter(self, event):
		self.text.config(cursor="hand2")

	def _leave(self, event):
		self.text.config(cursor="")

	def _click(self, event):
		for tag in self.text.tag_names(CURRENT):
			if tag[:7] == "xmltag-":
				self.links[tag](self.args[tag])
				return


def is_iterable(x):
	ret = True
	try:
		xit = iter(x)
	except TypeError as te:
		ret = False
	return True


class TextRO(tk.Text):
	def __init__(self, parent, *args, **kwargs):
		tk.Text.__init__(self, parent, *args, **kwargs)
		self.redirector = WidgetRedirector(self)
		self.insert = self.redirector.register("insert", lambda *args, **kw: "break")
		self.delete = self.redirector.register("delete", lambda *args, **kw: "break")


class WithCallback(object):
	def __init__(self, parent, *args, **kwargs):
		self.kwargs = kwargs
		self.callbacks = self.get_pop_kwargs('callbacks', [])
		self.parent = parent
		self.__dict__.update(self.kwargs)

	def get_pop_kwargs(self, key, defaultvalue):
		retval = defaultvalue
		try:
			retval = self.kwargs[key]
			self.kwargs.pop(key)
		except KeyError:
			pass
		return retval

	def callback(self, **kwargs):
		for c in self.callbacks:
			c(caller=self, **kwargs)


class TextFrame(tk.Frame, WithCallback):
	def __init__(self, parent, *args, **kwargs):
		WithCallback.__init__(self, parent, *args, **kwargs)
		self.ro = self.get_pop_kwargs('read_only', False)
		self.markers = self.get_pop_kwargs('markers', [])
		tk.Frame.__init__(self, parent, *args, **self.kwargs)
		self.pack(fill="both", expand=True)
		self.grid_propagate(False)
		self.grid_rowconfigure(0, weight=1)
		self.grid_columnconfigure(0, weight=1)
		# create a Text widget
		if self.ro:
			self.txtw = TextRO(self, borderwidth=3)
		else:
			self.txtw = tk.Text(self, borderwidth=3)
		# configure text widget
		self.setup(font_size=12, font_name="consolas")
		# layout
		self.txtw.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
		# to highlight http(s)
		self.hlink_manager = HyperlinkManager(self.txtw)
		# only to make tags clickable - not used in this one
		self.xmltag_manager = XMLTagManager(self.txtw)
		# create a Scrollbar and associate it with txt
		scrollb = tk.Scrollbar(self, command=self.txtw.yview)
		scrollb.grid(row=0, column=1, sticky='nsew')
		self.txtw['yscrollcommand'] = scrollb.set
		# what to highlight - used this func for xml tags
		self.highlight_tags = []
		self.update_tags(self.markers)
		self.poll_highlight()  # start polling the list

	def update_tags(self, markers=None):
		if markers:
			self.markers = []
			if is_iterable(markers) and not type(markers) == str:
				self.markers = markers
			else:
				self.markers.append(markers)
		self.txtw.tag_delete(self.highlight_tags)
		self.highlight_tags = []
		if not markers:
			return
		for im, m in enumerate(self.markers):
			logger.debug(' -m : {} '.format(m))
			self.highlight_tags.append(['ms{}'.format(im), m])
			self.txtw.tag_configure(self.highlight_tags[-1][0], background='yellow', foreground='red', underline=1)
		self.highlight()
		logger.debug('current markers: {} '.format(self.markers))

	def setup(self, **kwargs):
		if kwargs is not None:
			for key, value in kwargs.iteritems():
				if key == 'font_size':
					self.font_size = value
				if key == 'font_name':
					self.font_name = value
			self.txtw.config(font=(self.font_name, self.font_size), undo=True, wrap='word')

	def poll_highlight(self):
		self.highlight()
		self.after(5000, self.poll_highlight)

	def highlight(self, event=None):
		for _htag in self.highlight_tags:
			self.txtw.tag_remove(_htag[0], '1.0', 'end')
			count = tk.IntVar()
			self.txtw.mark_set('matchStart', '1.0')
			self.txtw.mark_set('matchEnd', '1.0')
			while True:
				index = self.txtw.search(_htag[1], 'matchEnd', 'end', count=count)
				if index == '':
					break  # no match was found
				self.txtw.mark_set('matchStart', index)
				self.txtw.mark_set('matchEnd', '%s+%sc' % (index, count.get()))
				self.txtw.tag_add(_htag[0], 'matchStart', 'matchEnd')

	def click_hyper_link(self, what=None):
		# print 'click on a link...', what
		if what:
			_confirm = tkMessageBox.askokcancel('Open?', '{}'.format(what))
			if _confirm:
				try:
					retcode = subprocess.call("open " + what, shell=True)
					if retcode < 0:
						logger.debug("Child was terminated by signal {}".format(-retcode))
					else:
						logger.debug("Child returned {}".format(retcode))
				except OSError, e:
					logger.error("Execution failed: {}".format(e))

	def click_xml_tag(self, what=None):
		self.callback(clicked_xml_tag=what)

	# def click_xml_tag(self, what=None):
	# 	if what:
	# 		_confirm = tkMessageBox.askokcancel('Selected tag', '{}'.format(what))
	# 		if _confirm:
	# 			logger.debug('diplay tag {}'.format(what))
	# 			for w in self.callback_widgets:
	# 				w.callback(self)

	def reset_text(self, stext):
		self.txtw.delete(1.0, tk.END)
		self.insert(stext)

	def insert(self, stext, marker=tk.END, linktags=['http://', 'https://']):
		_found_links_indexes = []
		for l in linktags:
			logger.debug('looking for {}'.format(l))
			_pos = 0
			_stext = stext
			while _pos < len(_stext):
				_s = _stext[_pos:]
				_idx = _s.find(l)
				if _idx >= 0:
					_found_links_indexes.append(_pos + _idx)
					_pos = _pos + _idx + len(_s[_idx:].split()[0]) + 1
					logger.debug('found {} at {}'.format(l, _pos + _idx))
				else:
					_pos = len(stext)
		_found_links_indexes.append(len(stext))
		_found_links_indexes.sort()
		_ci = 0
		for i in _found_links_indexes:
			s = stext[_ci:i]
			self.txtw.insert(marker, s)
			if i < len(stext):
				w = stext[i:].split()[0]
				if w:
					self.txtw.insert(marker, w, self.hlink_manager.add(self.click_hyper_link, w))
					_ci = i + len(w)

	def as_string(self):
		return self.txtw.get(1.0, tk.END)


class Dialog(tk.Frame, WithCallback):
	def __init__(self, parent, selections, *args, **kwargs):
		WithCallback.__init__(self, parent, *args, **kwargs)
		tk.Frame.__init__(self, parent, *args, **self.kwargs)
		self.list = tk.Listbox(self, selectmode=tk.EXTENDED)
		for s in selections:
			self.list.insert(tk.END, s)
		self.list.pack(fill=tk.BOTH, expand=1)
		self.current = None
		self.poll()  # start polling the list

	def poll(self):
		now = self.list.curselection()
		if now != self.current:
			self.list_change(now)
			self.current = now
		self.after(250, self.poll)

	def list_change(self, selection):
		self.variable.set(selection)
		self.callback()


class Options(tk.Frame, WithCallback):
	def __init__(self, parent, selections, *args, **kwargs):
		WithCallback.__init__(self, parent, *args, **kwargs)
		tk.Frame.__init__(self, parent, *args, **self.kwargs)
		self.variable = tk.StringVar(self)
		self.selections = selections
		if len(self.selections) < 1:
			self.selections = ['']
		logger.debug(self.selections[0])
		self.variable.set(self.selections[0])
		self.tsel = tuple(self.selections)
		self.list = tk.OptionMenu(self, self.variable, *self.tsel)
		self.list.pack(fill=tk.BOTH, expand=1)
		self.current = self.variable.get()
		self.poll()  # start polling the list

	def poll(self):
		now = self.variable.get()
		if now != self.current:
			self.list_change(self.variable.get())
			self.current = self.variable.get()
		self.after(500, self.poll)

	def list_change(self, selection):
		self.variable.set(selection)
		self.callback()

	def update_option_menu(self, selections):
		menu = self.list["menu"]
		menu.delete(0, "end")
		self.selections = selections
		for s in self.selections:
			menu.add_command(label=s,
							 command=lambda value=s: self.variable.set(value))
		if len(self.selections):
			self.variable.set(self.selections[0])


class XMLTreeView(tk.Frame, WithCallback):
	def __init__(self, parent, *args, **kwargs):
		WithCallback.__init__(self, parent, *args, **kwargs)
		self.xml_root = self.get_pop_kwargs('xml_root', None)
		self.debug = self.get_pop_kwargs('debug', None)
		tk.Frame.__init__(self, parent, *args, **self.kwargs)
		self.pack(fill="both", expand=True)
		self.grid_propagate(False)
		self.grid_rowconfigure(0, weight=1)
		self.grid_columnconfigure(0, weight=1)
		self.tview = ttk.Treeview(self)
		self.tview.heading('#0', text="XML Tree View")
		self.tview.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
		scrollb = tk.Scrollbar(self, command=self.tview.yview)
		scrollb.grid(row=0, column=1, sticky='nsew')
		self.tview['yscrollcommand'] = scrollb.set
		self.xml_tags = []
		self.bind("<Visibility>", self.on_visibility)

	def add_tree_items_recursive_debug(self, e, tv_parent):
		if not etree.iselement(e):
			return
		_s = []
		_s.append('tag:{} type:{}'.format(e.tag, type(e)))
		if e.text:
			_s.append('text({}):{}'.format(len(e.text), e.text))
		_newe = self.tview.insert(tv_parent, 'end', text=''.join(_s))
		if e.attrib:
			if len(e.attrib):
				for a in e.attrib:
					__newe = self.tview.insert(_newe, 'end', text=str(a))
					# logger.debug('dbg add attrib {}'.format(__newe))
		for ee in e:
			self.add_tree_items_recursive_debug(ee, _newe)

	def strip_blanks(self, s):
		rets = None
		if s:
			rets = s.replace(' ', '').replace('\n', '')
		return rets

	def add_tree_items_recursive(self, e, tv_parent, _open=False):
		if not etree.iselement(e):
			return
		_s = []
		if type(e) == etree._Element:
			_stag = '{}'.format(e.tag)
			_s.append(_stag)
			if _stag not in self.xml_tags:
				self.xml_tags.append(_stag)
		if type(e) == etree._Comment:
			_s.append('{}'.format('# '))
		if self.strip_blanks(e.text):
			# logger.debug('{} {} len is {}'.format(e.tag, e.text, len(self.strip_blanks(e.text))))
			if len(e.text.replace(' ', '')):
				if type(e) == etree._Element:
					_s.append(' = ')
				_s.append('{}'.format(e.text))
		_newe = self.tview.insert(tv_parent, 'end', text=''.join(_s), open=_open)
		if e.attrib:
			if len(e.attrib):
				for a in e.attrib:
					__newe = self.tview.insert(_newe, 'end', text=str(a))
					# logger.debug('add attrib {}'.format(__newe))
		for ee in e:
			self.add_tree_items_recursive(ee, _newe)  # subsequent leaves will be closed

	def update(self, new_root = None):
		for i in self.tview.get_children():
			self.tview.delete(i)
		if new_root is not None:
			self.xml_root = new_root
		if self.xml_root is not None:
			self.add_tree_items_recursive(self.xml_root, '', not self.debug)
			if self.debug:
				self.add_tree_items_recursive_debug(self.xml_root, '')
		logger.debug('number of items in the tree view: {}'.format(len(self.tview.get_children())))

	def on_visibility(self, event):
		self.update()


class XMLEditor(tk.Frame, WithCallback):
	def __init__(self, parent, pargs, *args, **kwargs):
		self.kwargs = kwargs
		self.markers = self.get_pop_kwargs('markers', [])
		tk.Frame.__init__(self, parent, *args, **self.kwargs)
		self.parent = parent
		self.args = pargs

		self.pack(fill="both", expand=True)
		# ensure a consistent GUI size
		self.grid_propagate(False)
		self.grid_rowconfigure(0, weight=100)
		self.grid_rowconfigure(1, weight=1)
		self.grid_rowconfigure(2, weight=1)

		self.grid_columnconfigure(0, weight=1)
		self.grid_columnconfigure(1, weight=1)
		self.grid_columnconfigure(2, weight=1)

		self.tabs = ttk.Notebook(self)
		self.tabs.grid(row=0, column=0, columnspan=4, sticky=tk.N + tk.S + tk.W + tk.E)

		self.edit_tags_tab = ttk.Frame(self.tabs)
		self.tview = XMLTreeView(self.edit_tags_tab, debug=self.args.debug)
		self.edit_tags_tab.pack(fill="both", expand=True)
		self.tabs.add(self.edit_tags_tab, text='View')

		self.edit_text_tab = ttk.Frame(self.tabs)
		self.edit = TextFrame(self.edit_text_tab, markers=self.markers, callbacks=[])
		# self.edit.grid(row=0, column=0, columnspan=1, sticky=tk.N + tk.S + tk.W + tk.E)
		self.edit.setup(font_size=12, font_name='fixed')
		self.edit_text_tab.pack(fill="both", expand=True)
		self.tabs.add(self.edit_text_tab, text='Edit File')
		# self.tabs.pack(expand=1, fill="both")
		# testing = not needed
		# self.tabs.bind("<<NotebookTabChanged>>", lambda event: event.widget.winfo_children()[event.widget.index("current")].update())
		self.tview.source = self.edit
		self.tview.source_type = 'widget'

		_sticky_button_expand = tk.N + tk.S + tk.W + tk.E
		# _sticky_button_expand = tk.W + tk.E

		logger.debug('{}'.format(str(self.tview.xml_tags)))
		self.tag_list = Options(self, selections=self.tview.xml_tags, callbacks=[self.update_tags])
		self.tag_list.grid(row=1, column=0, columnspan=1, sticky=_sticky_button_expand)

		self.button_xml = tk.Button(self, text='Parse XML', command=self.update_xml_string)
		self.button_xml.grid(row=1, column=1, columnspan=1, sticky=_sticky_button_expand)

		self.fname = pargs.fname
		self.label_xml = tk.Label(self, text='{}'.format(os.path.basename(self.fname)))
		self.label_xml.grid(row=1, column=2, columnspan=1, sticky=_sticky_button_expand)

		self.button_save = tk.Button(self, text='Save', command=self.save)
		self.button_save.grid(row=2, column=0, columnspan=1, sticky=_sticky_button_expand)

		self.button_save_close = tk.Button(self, text='Save&Close', command=self.save_close)
		self.button_save_close.grid(row=2, column=1, columnspan=1, sticky=_sticky_button_expand)

		self.button_close = tk.Button(self, text='Close', command=self.parent.destroy)
		self.button_close.grid(row=2, column=2, columnspan=7, sticky=_sticky_button_expand)

		self.sgrip = ttk.Sizegrip(self).grid(column=999, row=999, sticky=(tk.S, tk.E))

		self.xml_parser = etree.XMLParser(ns_clean=True, remove_blank_text=True)
		self.xml_root = None
		self.xml_string = '<?xml version="1.0"?>\n<root>\n<test>not much here</test>\n</root>'
		self.check_output()
		if self.fname:
			self.read_file()
		else:
			if pargs.xml_string:
				self.xml_string = pargs.xml_string
		self.process_xml()
		self.update_tags(self.tag_list)

	def check_output(self):
		if not os.path.isfile(self.fname):
			logger.warning('output file %s does not exist - making one...', self.fname)
			_confirm = tkMessageBox.showwarning('Failed opening file', 'Trying to make default output: {}'.format(str(self.fname)))
			if _confirm:
				pass
			try:
				with open(self.fname, 'w+') as f:
					f.writelines(self.xml_string)
					pass
			except IOError as e:
				logger.error('opening output failed with %s', str(e))
				_confirm = tkMessageBox.showerror('Failed opening file', 'opening output failed with %s'.format(str(e)))
				if _confirm:
					pass
				sys.exit(-1)

	def update_tags(self, caller=None, **kwargs):
		if caller == self.tag_list or caller is None:
			self.tview.update()
			_tag = self.tag_list.variable.get()
			logger.debug('tag: {}'.format(_tag))
			if _tag:
				self.edit.update_tags(['<' + _tag + '>', '<' + _tag, '</' + _tag, '</' + _tag + '>'])

	def callback(self, widget):
		self.focus()
		self.edit_tags_tab.focus()
		self.tview.reset()

	def fname_path(self):
		_path = os.path.join(self.args.outputdir, os.path.basename(self.fname))
		return _path

	def read_file(self, new_fname = None):
		if new_fname:
			self.fname = new_fname
		try:
			with open(self.fname, 'r') as f:
				cl = f.readlines()
				self.xml_string = ''.join(cl)
		except IOError as e:
			_confirm = tkMessageBox.showerror('Failed reading file', '{} : {}'.format(self.fname, str(e)))
			if _confirm:
				pass

	def update_xml_string(self):
		self.xml_string = self.edit.txtw.get(1.0, tk.END)
		self.process_xml()

	def process_xml(self):
		try:
			self.xml_root = etree.XML(self.xml_string, self.xml_parser)
			self.tview.update(self.xml_root)
			_preamb = self.xml_string.find('<{}>'.format(self.xml_root.tag))
			self.xml_string = '{}{}'.format(self.xml_string[:_preamb], etree.tostring(self.xml_root, pretty_print=True, method="xml"))
			self.edit.reset_text(self.xml_string)
			self.tag_list.update_option_menu(self.tview.xml_tags)
			self.update_tags(self.tag_list)
		except etree.XMLSyntaxError as e:
			_confirm = tkMessageBox.showerror('Failed parsing XML', '{}'.format(str(e)))
			if _confirm:
				pass


	def save(self):
		with open(self.fname, 'w') as f:
			stext = self.edit.txtw.get(1.0, tk.END)
			f.write(stext.encode('utf-8'))
			f.flush()

	def save_close(self):
		self.save()
		self.parent.destroy()


class App(tk.Tk):
	def __init__(self, parent, *args, **kwargs):
		tk.Tk.__init__(self, parent, *args, **kwargs)
		self.parent = parent

	# https://stackoverflow.com/questions/1892339/how-to-make-a-tkinter-window-jump-to-the-front
	def raise_app(self):
		self.attributes("-topmost", True)
		if platform.system() == 'Darwin':
			tmpl = 'tell application "System Events" to set frontmost of every process whose unix id is {} to true'
			script = tmpl.format(os.getpid())
			output = subprocess.check_call(['/usr/bin/osascript', '-e', script])
			if output:
				logger.warning('/usr/bin/osascript returned with {}'.format(output))
		self.after(0, lambda: self.attributes("-topmost", False))


# https://stackoverflow.com/questions/17466561/best-way-to-structure-a-tkinter-application
def runGUI(args, markers):
	app = App(None)
	app.minsize(width=800, height=600)
	app.title(os.path.basename(__file__) + ' @ ' + args.outputdir)
	ed = XMLEditor(app, args, width=20, height=20, markers=markers)
	ed.pack(side="top", fill="both", expand=True)
	app.raise_app()
	ed.edit.txtw.focus_set()
	app.mainloop()


def has_stdin():
	retval = False
	try:
		import select
		if select.select([sys.stdin, ], [], [], 0.0)[0]:
			retval = True
	except:
		pass
	return retval


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='popup text & clip', prog=os.path.basename(__file__))
	parser.add_argument('-i', '--stdin', help='stdin', action="store_true", default=False)
	parser.add_argument('-o', '--outputdir', help='output dir - tag can be just a file name; default is $PWD', type=str, default="$PWD")
	parser.add_argument('-d', '--dump', help='dump file', action="store_true")
	parser.add_argument('fname', help='file name to process', default='default.xml', nargs='?')
	parser.add_argument('-g', '--debug', help='debug on', default=False, action='store_true')
	parser.add_argument('-t', '--text', help='strings to process', default='')

	args = parser.parse_args()

	logging.basicConfig(stream=sys.stdout, level=logging.INFO)
	if args.debug:
		logger.setLevel(logging.DEBUG)

	args.outputdir = os.path.expandvars(args.outputdir)
	args.fname = os.path.expandvars(args.fname)

	stext = []
	if args.fname:
		try:
			cl = []
			with open(args.fname, 'r') as f:
				cl = f.readlines()
			for l in cl:
				stext.append(l)
		except IOError:
			pass

	if args.stdin or has_stdin():
		try:
			_btmp = True
			while _btmp:
				_btmp = sys.stdin.readline()
				stext.append(_btmp)
		except KeyboardInterrupt:
			sys.stdout.flush()
			pass
		with open('./tmp.xml', 'w') as f:
			f.writelines(stext)
		args.fname = './tmp.xml'

	args.text = ''.join(stext)
	# runGUI(' '.join(stext), args, markers=['<', '</', '>'])
	runGUI(args, markers=[])
