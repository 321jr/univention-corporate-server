#!/usr/bin/python3
from contextlib import contextmanager
import os
import os.path
import datetime
import logging
import time
import subprocess
import sys
import importlib
import tempfile
import shutil

logger = logging.getLogger(__name__)

def run_test_file(fname):
	with tempfile.NamedTemporaryFile(suffix='.py') as tmpfile:
		logger.info('Copying file to {}'.format(tmpfile.name))
		shutil.copy2(fname, tmpfile.name)
		with pip_modules(['pytest', 'selenium', 'xvfbwrapper', 'uritemplate']):
			importlib.reload(sys.modules[__name__])
			import pytest
			test_func = os.environ.get('UCS_TEST_ONE_TEST')
			if test_func:
				sys.exit(pytest.main([tmpfile.name + '::' + test_func, '-p', __name__, '-x', '--pdb']))
			else:
				pass
				sys.exit(pytest.main([tmpfile.name, '-p', __name__]))

@contextmanager
def pip_modules(modules):
	if os.environ.get('UCS_TEST_NO_PIP') == 'TRUE':
		yield
	if subprocess.run(['which', 'pip3'], stdout=subprocess.DEVNULL).returncode != 0:
		subprocess.check_call(['univention-install', '-y', 'python-pip3'], check=True)
	installed = subprocess.run(['pip3', 'list', '--format=columns'], stdout=subprocess.PIPE)
	logger.info(modules)
	for line in installed.stdout.splitlines()[2:]:
		mod, ver = line.decode('utf-8').strip().split()
		if mod in modules:
			modules.remove(mod)
		if '{}=={}'.format(mod, ver) in modules:
			modules.remove('{}=={}'.format(mod, ver))
	logger.info(modules)
	if modules:
		logger.info('Installing modules via pip3')
		logger.info('  {}'.format(' '.join(modules)))
		subprocess.check_output(['pip3', 'install'] + modules)
	try:
		yield
	finally:
		if modules:
			logger.info('Uninstalling modules via pip3')
			subprocess.check_output(['pip3', 'uninstall', '--yes'] + modules)

@contextmanager
def xserver():
	if os.environ.get('DISPLAY'):
		yield
	else:
		from xvfbwrapper import Xvfb
		with Xvfb(width=1280, height=720):
			yield

class Session(object):
	def __init__(self, base_url, screenshot_path, driver):
		self.base_url = base_url
		self.screenshot_path = screenshot_path
		self.driver = driver

	def __enter__(self):
		yield self

	def __exit__(self, exc_type, exc_value, traceback):
		try:
			self.save_screenshot('exit')
		finally:
			self.driver.quit()

	def __del__(self):
		self.driver.quit()

	def goto_portal(self):
		self.get('/univention/portal')
		time.sleep(2)
		self.click_element('#umc_menu_Button_0')
		time.sleep(1)
		self.click_element('#umcMenuLanguage')
		time.sleep(1)
		for element in self.find_all('#umcMenuLanguage__slide .menuItem'):
			if element.text == 'English':
				element.click()
				time.sleep(2)
				break

	def click_portal_tile(self, name):
		elements = self.find_all('.umcGalleryNameContent')
		for element in elements:
			if element.text == name:
				self.driver.execute_script("arguments[0].click();", element)
				break
		else:
			raise RuntimeError('Could not find {}'.format(name))

	@contextmanager
	def switched_frame(self, css):
		iframe = self.assert_one(css)
		self.driver.switch_to.frame(iframe)
		yield
		self.driver.switch_to.default_content()

	def get(self, url):
		if url.startswith('/'):
			url = self.base_url + url
		self.driver.get(url)

	def find_all(self, css):
		logger.info("Searching for %r", css)
		return self.driver.find_elements_by_css_selector(css)

	def find_first(self, css):
		elements = self.find_all(css)
		logger.info("Found %d elements", len(elements))
		if len(elements) == 0:
			return None
		return elements[0]

	def assert_one(self, css):
		elements = self.find_all(css)
		assert len(elements) == 1, 'len(elements) == {}'.format(len(elements))
		return elements[0]

	def click_element(self, css):
		self.assert_one(css).click()

	def enter_input(self, input_name, value):
		self.enter_input_element('[name={}]'.format(input_name), value)

	def enter_input_element(self, css, value):
		elem = self.assert_one(css)
		elem.clear()
		elem.send_keys(value)

	def save_screenshot(self, name):
		timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
		os.makedirs(self.screenshot_path, exist_ok=True)
		filename = os.path.join(self.screenshot_path, '%s_%s.png' % (name, timestamp))
		logger.info('Saving screenshot %r', filename)
		self.driver.save_screenshot(filename)

	@classmethod
	def chrome(cls, base_url, screenshot_path):
		from selenium import webdriver
		options = webdriver.ChromeOptions()
		options.add_argument('--no-sandbox')  # chrome complains about being executed as root
		driver = webdriver.Chrome(options=options)
		return cls(base_url, screenshot_path, driver)

	@classmethod
	@contextmanager
	def running_chrome(cls, base_url, screenshot_path):
		with xserver():
			obj = cls.chrome(base_url, screenshot_path)
			with obj:
				yield obj

try:
	import pytest
except ImportError:
	pass
else:
	@pytest.fixture(scope='session')
	def config():
		"""Test wide Configuration aka UCR
		Used to get some defaults if not environment variables are
		given. But if UCR is not avaiable, returns an empty dict...
		"""
		try:
			from univention.config_registry import ConfigRegistry
			ucr = ConfigRegistry()
			ucr.load()
			return dict(ucr)
		except ImportError:
			return {}

	@pytest.fixture(scope='session')
	def hostname(config):
		"""Hostname to test against"""
		ret = os.environ.get('UCS_TEST_HOSTNAME')
		if ret is None:
			if config:
				ret = 'https://{hostname}.{domainname}'.format(**config)
			else:
				logger.warning('$UCS_TEST_HOSTNAME not set')
				ret = 'http://localhost'
		return ret

	@pytest.fixture(scope='session')
	def admin_username(config):
		"""Username of the Admin account"""
		ret = os.environ.get('UCS_TEST_ADMIN_USERNAME')
		if not ret:
			ret = config.get('tests/domainadmin/account')
			if ret:
				ret = ret.split(',')[0].split('=')[-1]
			else:
				ret = 'Administrator'
		return ret

	@pytest.fixture(scope='session')
	def admin_password(config):
		"""Password of the Admin account"""
		ret = os.environ.get('UCS_TEST_ADMIN_USERNAME')
		ret = os.environ.get('UCS_TEST_ADMIN_PASSWORD')
		if not ret:
			ret = config.get('tests/domainadmin/pwd', 'univention')
		return ret

	@pytest.fixture(scope='session')
	def udm(hostname, config, admin_username, admin_password):
		"""A UDM instance (REST client)"""
		rest_lib = os.environ.get('UCS_TEST_REST_CLIENT_LIB', 'univention.testing._udm_rest')
		try:
			rest_lib = importlib.import_module(rest_lib)
		except ImportError:
			logger.critical('Could not import {}. Maybe set $UCS_TEST_REST_CLIENT_LIB'.format(rest_lib))
			raise
		uri = os.environ.get('UCS_TEST_UDM_URI')
		if not uri:
			if config:
				hostname = 'https://{}'.format(config.get('ldap/master'))
			else:
				logger.warning('$UCS_TEST_UDM_URI not set')
			uri = '{}/univention/udm/'.format(hostname)
		udm = rest_lib.UDM.http(uri, admin_username, admin_password)
		return udm

	@pytest.fixture(scope='session')
	def users(udm):
		user_mod = udm.get('users/user')
		users = {}
		user_id_cache = {'X': 1}
		def _users(user_id=None, attrs={}):
			username = attrs.get('username')
			if username is None:
				if user_id is None:
					user_id = user_id_cache['X']
					user_id_cache['X'] += 1
				username = 'ucs-test-user-{}'.format(user_id)
			if username not in users:
				user = user_mod.new()
				user.properties.update(attrs)
				if user.properties['username'] is None:
					user.properties['username'] = username
				if user.properties['firstname'] is None:
					user.properties['firstname'] = 'John'
				if user.properties['lastname'] is None:
					user.properties['lastname'] = user.properties['username']
				if user.properties['password'] is None:
					user.properties['password'] = 'univention'
				user.save()
				users[username] = user
			return users[username]
		try:
			yield _users
		finally:
			for user in users.values():
				user.delete()

	@pytest.fixture
	def new_user(users):
		"""Creates a new user and cleans up"""
		user = users()
		return user

	@pytest.fixture(scope='session')
	def db_conn():
		"""A database connection object (sqlalchemy)"""
		import sqlalchemy
		ret = os.environ.get('UCS_TEST_DB_URI')
		if not ret:
			logger.warning('$UCS_TEST_DB_URI not set')
			raise ValueError('Need $UCS_TEST_DB_URI')
		engine = sqlalchemy.create_engine(ret)
		with engine.connect() as conn:
			yield conn

	@pytest.fixture(scope='session')
	def selenium_base_url():
		"""Base URL for selenium"""
		ret = os.environ.get('UCS_TEST_SELENIUM_BASE_URL')
		if ret is None:
			logger.warning('$UCS_TEST_SELENIUM_BASE_URL not set')
			ret = 'http://localhost'
			logger.warning('  using {}'.format(ret))
		return ret

	@pytest.fixture(scope='session')
	def selenium_screenshot_path():
		"""Path where selenium should save screenshots"""
		ret = os.environ.get('UCS_TEST_SELENIUM_SCREENSHOT_PATH')
		if ret is None:
			logger.warning('$UCS_TEST_SELENIUM_SCREENSHOT_PATH not set')
			ret = 'selenium'
			logger.warning('  using {}'.format(ret))
		return ret

	@pytest.fixture
	def chrome(selenium_base_url, selenium_screenshot_path):
		"""A running chrome instance, controllable by selenium"""
		with Session.running_chrome(selenium_base_url, selenium_screenshot_path) as c:
			yield c
