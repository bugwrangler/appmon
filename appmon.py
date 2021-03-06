import os, sys, argparse, time, codecs, binascii, frida, json, traceback
from flask import Flask, request, render_template
from termcolor import colored
import database as db

app = Flask(__name__)
app.debug = True

device = ''
session = ''
merged_script_path = '/tmp/merged.js'

APP_LIST = []

@app.route('/api/fetch', methods=['GET'])
def serve_json():
	index = request.args.get('id')
	db_name = request.args.get('app')
	response = db.read_from_database(db_name, index)
	#response = open('static/data.json').read()
	return response

@app.route('/monitor/', methods=['GET'])
def monitor_page():
	app_name = request.args.get('app')
	return render_template('monitor.html', app_name=app_name)

@app.route('/', methods=['GET'])
def landing_page():
	global APP_LIST
	global DB_MAP

	for root, dirs, files in os.walk('./app_dumps'):
		path = root.split('/')
		for file in files:
			file_path = os.path.join(root, file)
			if file_path.endswith('.db'):
				APP_LIST.append(file.replace('.db', ''))

	return render_template('index.html', apps=APP_LIST)

def init_opts():
	parser = argparse.ArgumentParser()
	parser.add_argument('-a', action='store', dest='app_name', default='',
                    help='''Process Name;
                    Accepts "Twitter" for iOS; 
                    "com.twitter.android" for Android; "Twitter" for MacOS X''')
	parser.add_argument('-p', action='store', dest='platform',
                    help='Platform Type; Accepts "ios", "android" or "mac"')
	parser.add_argument('-s', action='store', dest='script_path', default='',
                    help='''Path to agent script file;
                    Can be relative/absolute path for a file or directory;
                    Multiple scripts in a directory shall be merged;
                    Needs "-a APP_NAME"''')
	parser.add_argument('-o', action='store', dest='output_dir',
                    help='''(Optional) Path to store any dumps/logs;
                    Accepts relative/absolute paths''')
	parser.add_argument('-ls', action='store', dest='list_apps', default=0,
                    help='''Optional; Accepts 1 or 0; Lists running Apps on target device; Needs "-p PLATFORM"''')
	parser.add_argument('-v', action='version', version='AppMon v0.1, Nishant Das Patnaik, 2016')

	if len(sys.argv) == 1:
		parser.print_help()
		sys.exit(1)

	results = parser.parse_args()
	app_name = results.app_name
	platform = results.platform
	script_path = results.script_path
	list_apps = results.list_apps
	output_dir = results.output_dir if results.output_dir else './app_dumps'

	if script_path != None and app_name == '' and list_apps == 0:
		parser.print_help()
		sys.exit(1)

	return app_name, platform, script_path, list_apps, output_dir

def merge_scripts(path):
	global merged_script_path
	script_source = ''
	for root, dirs, files in os.walk(path):
		path = root.split('/')
		for file in files:
			script_path = os.path.join(root, file)
			if script_path.endswith('.js'):
				source = ''
				with codecs.open(script_path, 'r', 'utf-8') as f:
					source = f.read()
				script_source += '/* ____%s/%s____ */\n\n' % (os.path.basename(root), file) + source + '\n\n'
	with codecs.open(merged_script_path, "w", "utf-8") as f:
		f.write(script_source)
	return merged_script_path

def _exit_():
	print colored('[INFO] Exiting...', 'green')
	try:
		os.remove(merged_script_path)
	except Exception as e:
		pass
	sys.exit(1)

def writeBinFile(fname, data):
	with codecs.open(fname, "a", "utf-8") as f:
		f.write(data + '\r\n\r\n')

def list_processes(session):
	print 'PID\tProcesses\n', '===\t========='
	for app in session.enumerate_processes():
		print "%s\t%s" % (app.pid, app.name)

def on_detached():
	print colored('[WARNING] "%s" has terminated!' % (app_name), 'red')

def on_message(message, data):
    current_time = time.strftime("%H:%M:%S", time.localtime())
    global output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if message['type'] == 'send':
        writePath = os.path.join(output_dir, app_name + '.db')
        db.save_to_database(writePath, message['payload'])
        #writePath = os.path.join(output_dir, app_name + '.json')
        #writeBinFile(writePath, message['payload']) #writeBinFile(writePath, binascii.unhexlify(message['payload']))
        print colored('[%s] Dumped to %s' % (current_time, writePath), 'green')
    elif message['type'] == 'error':
        print(message['stack'])

def generate_injection():
	injection_source = ''
	if os.path.isfile(script_path):
		with codecs.open(script_path, 'r', 'utf-8') as f:
			injection_source = f.read()
	elif os.path.isdir(script_path):
		with codecs.open(merge_scripts(script_path), 'r', 'utf-8') as f:
			injection_source = f.read()
	print colored('[INFO] Building injection...', 'yellow')
	return injection_source

def init_session():
	try:
		session = None
		if platform == 'ios' or platform == 'android':
			device = frida.get_usb_device()
		elif platform == 'mac':
			device = frida.get_local_device()
		else:
			print colored('[ERROR] Unsupported platform', 'red')
			sys.exit()
		if app_name:
			try:
				session = device.attach(app_name)
			except Exception as e:
				print colored('[ERROR] ' + str(e), 'red')
				traceback.print_exc()
		if session:
			print colored('[INFO] Attached to %s' % (app_name), 'yellow')
			session.on('detached', on_detached)
	except Exception as e:
		print colored('[ERROR] ' + str(e), 'red')
		traceback.print_exc()
		sys.exit(1)
	return device, session

try:
	app_name, platform, script_path, list_apps, output_dir = init_opts()
	device, session = init_session()

	if int(list_apps) == 1:
		list_processes(device)
		sys.exit(1)

	if session:
		script = session.create_script(generate_injection())
		if script:
			print colored('[INFO] Instrumentation started...', 'yellow')
			script.on('message', on_message)
			script.load()
			app.run() #Start WebServer
except Exception as e:
	print colored('[ERROR] ' + str(e), 'red')
	traceback.print_exc()
	sys.exit(1)

try:
    while True:
    	pass
except KeyboardInterrupt:
    _exit_()