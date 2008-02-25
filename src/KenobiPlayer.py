# Author: Douglas Fernando da Silva - doug.fernando at gmail.com
# Copyright 2008
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from random import shuffle
import appuifw
import audio
import e32
import e32db
import md5
import os
import time
import urllib
import socket

#### ----------- Model ------------------------------ # 

class MusicsFactory(object):
	def __init__(self):
		self.__all_musics = []
	
	# BUG Unicode error for strange files paths
	def load_directory_musics(self, arg, dirname, names):
		mp3_files = filter(lambda n: n.endswith(".mp3"), map(unicode, names))

		for name in mp3_files:
			music_path = os.path.join(dirname, unicode(name))
			music = Music(music_path)
			self.__all_musics.append(music)
		
	def load_all_musics(self, root_path):
		os.path.walk(root_path, self.load_directory_musics, None)

		return self.__all_musics

class Music(object):
	def __init__(self, file_path=""):
		self.file_path = file_path;
		self.init_music()
		self.player = MusicPlayer(self)
		self.length = 0
		self.number = ""
		self.music_brainz_ID = ""
		self.played_at = 0
		self.position = 0
	
	def init_music(self):
		if self.file_path:
			fp = open(self.file_path, "r")
			fp.seek(-128, 2)
			fp.read(3)
	
			self.title = self.remove_X00(fp.read(30))
			self.artist = self.remove_X00(fp.read(30))
			self.album = self.remove_X00(fp.read(30))
			self.year = self.remove_X00(fp.read(4))
			self.comment = self.remove_X00(fp.read(28))
	
			fp.close()
		else:
			self.title = None
			self.artist = None
			self.album = None
			self.year = None
			self.comment = None
	
	def remove_X00(self, value):
		return value.replace("\x00", "")
	
	def __str__(self):
		return u"  Artist: %s\n  Title: %s\n  Album: %s\n  Path: %s" % (self.artist, self.title, self.album, self.file_path)

	def play(self, callback):
		self.player.play(callback)
	
	def stop(self):
		self.player.stop()
		
	def pause(self):
		self.player.pause()
		
	def volume_up(self):
		self.player.volume_up()

	def volume_down(self):
		self.player.volume_down()

	def is_playing(self):
		return self.player.is_playing()

	def can_update_position(self):
		curr_pos = int(self.player.current_position() / 1e6)
		if self.position != curr_pos:
			self.position = curr_pos
			return True
	
		return False

	def current_position_formatted(self):
		return self.format_secs_to_str(self.position)
	
	def length_formatted(self):
		return self.format_secs_to_str(self.length)
	
	def format_secs_to_str(self, value):
		hours = value / 3600
		
		seconds_remaining = value % 3600
		
		minutes = seconds_remaining / 60
		
		if minutes > 1:
			seconds = minutes % 60
		else:
			seconds = value % 60

		if hours >= 1:
			return unicode("%02i:%02i:%02i" % (hours, minutes, seconds))
		else:
			return unicode("%02i:%02i" % (minutes, seconds))
		

class MusicPlayer(object):
	current_volume = -1

	def __init__(self, music):
		self.__music = music
		self.__paused = False
		self.__loaded = False
		self.__player = None
		self.__current_position = None
	
	def play(self, callback=None):
		if not self.__paused:
			self.__player = audio.Sound.open(self.__music.file_path)
			self.configure_volume()
			self.__music.length = int(self.__player.duration() / 1e6)
			self.__music.played_at = int(time.time())
			self.__loaded = True
		else:
			self.__player.set_position(self.__current_position)
		
		self.__player.play(times=1, interval=0, callback=callback)

	def configure_volume(self):
		# HACK, I don't know why, but using directly the class attribute does not work
		volume = self.__class__.current_volume 
		if volume < 0: # default value = -1
			default_volume = self.__player.max_volume() / 4
			self.__class__.current_volume = default_volume

		self.__volume_step = self.__player.max_volume() / 10 # TODO maybe it can be a constant
		self.__player.set_volume(self.__class__.current_volume)
		
	def stop(self):
		if self.__loaded:
			self.__player.stop()
			self.__player.close()
			self.__loaded = False
	
	def pause(self):
		if self.__loaded:
			self.__current_position = player.current_position()
			self.__player.stop()
			self.__paused = True

	def volume_up(self):
		if self.__loaded:
			self.__class__.current_volume = self.__class__.current_volume + self.__volume_step
			if self.__class__.current_volume > self.__player.max_volume(): 
				self.__class__.current_volume = self.__player.max_volume()
			
			self.__player.set_volume(self.__class__.current_volume)
	
	def volume_down(self):
		if self.__loaded:
			self.__class__.current_volume = self.__player.current_volume() - self.__volume_step
			if self.__class__.current_volume < 0:
				self.__class__.current_volume = 0
			
			self.__player.set_volume(self.__class__.current_volume)

	def is_playing(self):
		return self.__player.state() == 2

	def current_volume_percentage(self):
		return (self.__class__.current_volume / self.__player.max_volume()) * 100
	
	def can_be_added_to_history(self):
		min_length_cond = self.__player.current_position() > 30e6
		min_length_played_cond = (self.__player.current_position() > 240e6 or
			float(self.__player.current_position()) / float(self.__player.duration()) > 0.5)
		
		return min_length_cond and min_length_played_cond

	def current_position(self):
		return self.__player.current_position()

# TODO This class has a bad name, it must be renamed	
class MusicList(object):
	def __init__(self, music_factory, root_path, listener, random = False):
		self.__timer = e32.Ao_timer()
		self.__listener = listener
		self.__should_stop = False
		self.__current_index = 0
		
		self.__musics = music_factory.load_all_musics(root_path)

		if self.__musics:
			if random: 
				shuffle(self.__musics)
			
			self.current_music = self.__musics[0]
		else:
			self.current_music = None
	
	def play(self):
		self.__should_stop = False
		
		while self.current_music != None:
			self.current_music.play(self.play_callback)
			self.__listener.update_music(self.current_music)

			added_to_history = False;
			while self.current_music.is_playing():
				if not added_to_history:
					if self.current_music.player.can_be_added_to_history():
						print 'Now it can be added'
						self.__listener.add_to_history(self.current_music)
						added_to_history = True
				
				if self.current_music.can_update_position():
					self.__listener.update_music(self.current_music)
				
				e32.ao_yield()

			self.__listener.finished_music(self.current_music)

			if self.__should_stop: break
			
			self.move_next()
			self.__timer.after(0.3)
	
	def play_callback(self, current, previous, err):
		pass
		
	def stop(self):
		self.__should_stop = True
		if self.current_music: 
			was_playing = self.current_music.is_playing()
			self.current_music.stop()
			if was_playing:
				self.__listener.finished_music(self.current_music)

	def next(self):
		self.stop()
		self.move_next()
		self.play()
		
	def previous(self):
		self.stop()
		self.move_previous()
		self.play()

	def move_next(self):
		last_index = len(self.__musics) - 1
		if self.__current_index < last_index:
			self.__current_index = self.__current_index + 1
		else:
			self.__current_index = last_index
		self.current_music = self.__musics[self.__current_index]
	
	def move_previous(self):
		if self.__current_index > 0:
			self.__current_index = self.__current_index - 1
		else:
			self.__current_index = 0
		self.current_music = self.__musics[self.__current_index]

	def current_position_formated(self):
		return unicode("%i / %i" % (self.__current_index + 1, len(self.__musics)))

class MusicHistory(object):
	def __init__(self, repository, audio_scrobbler_service):
		self.batch_size = 50
		self.repository = repository
		self.__audio_scrobbler_service = audio_scrobbler_service

	def add_music(self, music):
		print 'Added to history %s' % (music.title)
		self.repository.save_music(music)
	
	def clear(self):
		self.repository.clear_history()
	
	def send_to_audioscrobbler(self):
		musics = self.repository.load_all_history()
		if musics and len(musics) < self.batch_size:
			self.__audio_scrobbler_service.send(musics)
			self.clear()
		elif musics:
			self.send_batches_to_audioscrobbler(musics)

	def send_batches_to_audioscrobbler(self, musics):
		assert len(musics) >= self.batch_size
		
		num_full_batches = len(musics) / self.batch_size
		for i in range(num_full_batches):
			start = i * self.batch_size
			end = start + self.batch_size
			batch = musics[start:end]
			self.send_batch(batch)
		
		remainings = len(musics) % self.batch_size
		if remainings > 0:
			batch = musics[len(musics)-remainings:len(musics)]
			self.send_batch(batch)
		
	def send_batch(self, musics_batch):
		self.__audio_scrobbler_service.send(musics_batch)
		self.repository.remove_musics(musics_batch)


class AudioScrobblerUser(object):
	def __init__(self, username, password, hashed=False):
		self.username = username
		if not hashed:
			self.password = md5.md5(password).hexdigest()
		else:
			self.password = password

#### ----------- Repositories ------------------------------ #

class AudioScrobblerUserRepository(object):
	def __init__(self, db_helper):
		self.db_helper = db_helper

	def load(self):
		cmd = "SELECT UserName, Password FROM User"
		rows = self.db_helper.execute_reader(cmd)
		if rows:
			return AudioScrobblerUser(rows[0][0], rows[0][1], True)
		
		return None
	
	def save(self, user):
		remove_cmd = "DELETE FROM USER"
		insert_cmd = "INSERT INTO User (UserName, Password) VALUES('%s', '%s')" % (user.username, user.password)

		result = self.db_helper.execute_nonquery(remove_cmd)
		result = self.db_helper.execute_nonquery(insert_cmd)
		assert result > 0
	

# TODO close the db	
class MusicHistoryRepository(object):
	def __init__(self, db_helper):
		self.db_helper = db_helper
	
	def save_music(self, music):
		cmd = "INSERT INTO Music_History (Artist, Track, PlayedAt, Album, TrackLength) VALUES('%s', '%s', %i, '%s', %i)" % \
				(music.artist.replace("'", "''"), music.title.replace("'", "''"), 
					music.played_at, music.album.replace("'", "''"), music.length)
		
		result = self.db_helper.execute_nonquery(cmd)
		assert result > 0

	def remove_musics(self, musics):
		for music in musics:
			cmd = "DELETE FROM Music_History WHERE PlayedAt = %i" % (music.played_at)
			self.db_helper.execute_nonquery(cmd)
	
	def clear_history(self):
		cmd = "DELETE FROM Music_History"
		self.db_helper.execute_nonquery(cmd)
	
	def load_all_history(self):
		cmd = "SELECT Artist, Track, PlayedAt, Album, TrackLength FROM Music_History"
		rows = self.db_helper.execute_reader(cmd)
		result = []
		for row in rows:
			music = Music()
			music.artist = row[0]
			music.title = row[1]
			music.played_at = row[2]
			music.album = row[3]
			music.length = row[4]
			result.append(music)
	
		return result




#### ----------- Services ------------------------------ #	

class AudioScrobblerError(Exception):
	pass

class NoAudioScrobblerUserError(Exception):
	pass

class AudioScrobblerService(object):
	def __init__(self, user_repository): 
		self.user_repository = user_repository
		self.logged = False
		self.handshake_url = "http://post.audioscrobbler.com/"
		self.handshake_data = None
		self.session_id = None
		self.now_url = None
		self.post_url = None
		self.user = None
		
	def create_handshake_data(self):
		user = self.user_repository.load()
		if not user:
			raise NoAudioScrobblerUserError("You must set an user/password first")
		
		client_id = "tst"
		client_version = "1.0"
		tstamp = int(time.time())
		token  = md5.md5("%s%d" % (self.password, tstamp)).hexdigest()
   		
   		values = {
			"hs": "true", 
         	"p": '1.2', 
         	"c": client_id, 
         	"v": client_version, 
         	"u": self.username, 
         	"t": tstamp, 
         	"a": token
	 	}
   		
   		self.handshake_data = urllib.urlencode(values)

	def login(self):
		self.create_handshake_data()
		response = urllib.urlopen("%s?%s" % (self.handshake_url, self.handshake_data))
		self.session_id, self.now_url, self.post_url = self.handle_handshake_response(response)
		self.logged = True
		
		print "%s %s %s" % (self.session_id, self.now_url, self.post_url)
	
	def handle_handshake_response(self, response):
		result = response.read()
		lines = result.split("\n")

		if lines[0] == "OK":
			return (lines[1], lines[2], lines[3])
		else:
			self.handle_handshake_error(lines[0])
		
	def handle_handshake_error(self, error):
		if error == "BADAUTH":
			raise AudioScrobblerError("Bad username/password")
		elif error == "BANNED":
			raise AudioScrobblerError("'This client-version was banned by Audioscrobbler. Please contact the author of this module!'")
		elif error == "BADTIME":
			raise AudioScrobblerError("'Your system time is out of sync with Audioscrobbler. Consider using an NTP-client to keep you system time in sync.'")
		elif error.startswith("FAILED"):
	  		raise AudioScrobblerError("Authencitation with AS failed. Reason: %s" % error)
		else:
			raise AudioScrobblerError("Authencitation with AS failed.")
	
	def check_login(self):
		if not self.logged:
			raise Exception("You must be logged to execute this operation")
		
	def now_playing(self, music):
		self.check_login()
		
		values = {
			"s": self.session_id, 
			"a": unicode(music.artist).encode("utf-8"), 
			"t": unicode(music.title).encode("utf-8"), 
			"b": unicode(music.album).encode("utf-8"), 
			"l": music.length, 
			"n": music.number, 
			"m": music.music_brainz_ID
		}

		data = urllib.urlencode(values)

		response = urllib.urlopen(self.now_url, data)
		result = response.read()
	
		if result.strip() == "OK":
			print 'Sent Now Playing %s' % (music.title)
			return True
		elif result.strip() == "BADSESSION":
			raise AudioScrobblerError("Invalid session")
		else:
			return False
	
	def send(self, musics):
		self.check_login()
		
		data = self.create_send_music_data(musics)
		
		response = urllib.urlopen(self.post_url, data)
		result = response.read()
		result_value = result.split("\n")[0]

		if result_value == "OK":
			for music in musics:
				print 'Scrobbled %s' % (music.title)
			
			return True
		elif result_value.startswith("FAILED"):
			raise AudioScrobblerError("Submission to AS failed. Reason: %s" % result_value)
		else:
			return False

	def create_send_music_data(self, musics):
		musics_data = []
		
		for music in musics:
			musics_data.append({ 
				"a": unicode(music.artist).encode("utf-8"), 
				"t": unicode(music.title).encode("utf-8"), 
				"i": music.played_at, 
				"o": "P", 
				"r": "", 
				"l": music.length, 
				"b": unicode(music.album).encode("utf-8"), 
				"n": music.number, 
				"m": music.music_brainz_ID
			})

		values = {}
		
		i = 0
		for item in musics_data:
			for key in item:
				values[key + ("[%d]" % i)] = item[key]
			i = i + 1
			
		values["s"] = self.session_id

		data = urllib.urlencode(values)
		
		return data

#### ----------- Infra ------------------------------ #

class DbHelper(object):
	def __init__(self, dbpath):
		self.dbpath = dbpath
		db_already_exists = os.path.exists(self.dbpath) 
		
		self.db = e32db.Dbms()
		self.dbv = e32db.Db_view()
		
		try:
			self.db.open(unicode(dbpath))
		except:
			self.db.create(unicode(dbpath))
			self.db.open(unicode(dbpath))
			self.create_tables()

	def execute_nonquery(self, sql):
		return self.db.execute(unicode(sql))

	def execute_reader(self, sql):
		self.dbv.prepare(self.db, unicode(sql))
		self.dbv.first_line()
		result = []
		
		for i in range(self.dbv.count_line()):
			self.dbv.get_line()
			row = []
			
			for i in range(self.dbv.col_count()):
				try:
					row.append(self.dbv.col(i+1))
				except:    # in case coltype 16
					row.append(None)
			
			result.append(row)
			self.dbv.next_line()
		
		return result

	def create_tables(self):
		self.create_music_history_table()
		self.create_user_table()
	
	def create_music_history_table(self):
		cmd = "CREATE TABLE Music_History (Artist varchar(200), Track varchar(200), PlayedAt integer, Album varchar(200), TrackLength integer)"
		self.execute_nonquery(cmd)

	def create_user_table(self):
		cmd = "CREATE TABLE User (UserName varchar(200), Password varchar(200))"
		self.execute_nonquery(cmd)

#### ----------- Testing ------------------------------ #
class Fixtures(object):
	def __init__(self):
		pass
		
	def run(self):
#		self.db_tests()
		self.as_tests()
	
	def as_tests(self):
		as_service = AudioScrobblerService("doug_fernando", "sko445")
		as_service.login()
		music = Music("E:\\Music\\Bloc Party - Silent Alarm\\01 - Like Eating Glass.mp3")
		music.length = 261
		music.played_at = int(time.time()) - 40
		print "Sent %s" % (as_service.send([music]))
	
	def db_tests(self):
		repos = MusicHistoryRepository("c:\\data\\kenobi_player\\history.db")
		repos.clear_history()

		music = Music("E:\\Music\\Bloc Party - Silent Alarm\\01 - Like Eating Glass.mp3")
		music.length = 261
		music.played_at = int(time.time()) - 40

		repos.save_music(music)
		musics = repos.load_all_history()
		
		for amusic in musics:
			print amusic


#### ----------- UI ------------------------------ #


class PlayerUI(object):
	def __init__(self, music_factory, music_history, audio_scrobbler_service):
		self.__music_factory = music_factory
		self.__applock = e32.Ao_lock()
		self.__music_history = music_history
		self.__audio_scrobbler_service = audio_scrobbler_service
		self.__ap_services = AccessPointServices()
		self.__default_font = None
		self.__default_body = None
		self.__selecting_directory = False
		self.__directory_selector = DirectorySelector(lambda dir: self.set_selected_directory(dir))
		self.selected_directory = None
		self.music_list = None
		
		self.basic_config()
		self.init_menus()
		self.init_background()
		self.config_events()
	
	def basic_config(self):
		appuifw.app.screen='normal'
		appuifw.app.title = u"Aclumbático PLAYER"
	
	def init_menus(self):
		appuifw.app.menu = [(u"Select the Music DIR", self.select_directory), 
							(u"Controls", (
								(u"Play", self.play), 
								(u"Stop", self.stop), 
								(u"Previous", self.previous), 
								(u"Next", self.next))), 
							(u"Volume", 
									((u"Up", self.volume_up), (u"Down", self.volume_down))), 
							(u"LastFm", 	(
								(u"Connect", self.connect), 
								(u"Clear History", self.clear_as_db), 
								(u"Submit History", self.send_history))), 
							(u"Tests", self.test), 
							(u"Exit", self.quit)]
		
	def test(self):
		Fixtures().run()
	
	def init_background(self):
		t = appuifw.Text()
		appuifw.app.body = t
		self.__default_font = t.font
		t.set(u"Please select a directory using the menu")
	
	def config_events(self):
		appuifw.app.exit_key_handler = self.quit
	
	def quit(self):
		self.stop()
		self.__applock.signal()
	
	def clear_as_db(self):
		self.__music_history.clear()
	
	def connect(self):
		if not self.is_online():
			self.__ap_services.set_accesspoint()
			self.long_operation(lambda: self.__audio_scrobbler_service.login())
	
	def send_history(self):
		if not self.is_online():
			self.connect()
		
		self.__music_history.send_to_audioscrobbler()
	
	def play(self): 
		if self.check_selected_directory():
			self.music_list.play()
	
	def long_operation(self, operation):
		operation()
	
	def stop(self):
		if self.music_list:	
			self.music_list.stop()
			
	def next(self):
		if self.music_list:	
			self.music_list.next()

	def previous(self):
		if self.music_list:	
			self.music_list.previous()

	def volume_up(self):
		if self.music_list:	
			self.music_list.current_music.volume_up()
			self.show_current_volume()

	def show_current_volume(self):
		i = appuifw.InfoPopup()
		i.show(u"Current_volume: %s" % self.music_list.current_music.player.current_volume_percentage(), 
				(50, 50), 5000, 0, appuifw.EHLeftVTop)
		
	def volume_down(self):
		if self.music_list:	
			self.music_list.current_music.volume_down()
			self.show_current_volume()
		
	def select_directory(self): 
		self.__default_body = (appuifw.app.body, appuifw.app.menu) 
		self.__directory_selector.init()
		lb = self.__directory_selector.run()
		self.__selecting_directory = True
		appuifw.app.body = lb
		appuifw.app.menu = [
						(u"Selecionar", self.__directory_selector.select_dir),
						(u"Cancelar", self.set_selected_directory)]
	
	def set_selected_directory(self, dir=None):
		if dir:
			self.selected_directory = dir

		appuifw.app.body, appuifw.app.menu = self.__default_body
		self.__selecting_directory = False
		self.update_directory()
	
	def update_directory(self):
		if self.music_list:
			self.music_list.stop()
		
		self.music_list = MusicList(self.__music_factory, self.selected_directory, self, True)
		self.play()
	
	def finished_music(self, music):
		if self.is_online():
			self.__music_history.send_to_audioscrobbler()
	
	def update_music(self, music):
		if not self.__selecting_directory:
			t = appuifw.app.body 
			t.set(u"")
			t.font = self.__default_font
			t.color = (255, 0, 0)
			t.style = appuifw.STYLE_BOLD
			t.add(u"Current Playing:\n\n")
			t.color = 0
			t.style = appuifw.STYLE_ITALIC | appuifw.STYLE_BOLD 
			t.add(unicode("  Artist: %s\n" % music.artist))
			t.add(unicode("  Track: %s\n\n" % music.title))
			t.font = u"albi10b"
			t.add(unicode("  %s - %s\n\n" % (music.current_position_formatted(), music.length_formatted())))
			t.font = u"albi9b"
			t.add(unicode("  %s" % self.music_list.current_position_formated()))
			
			self.audio_scrobbler_now_playing(music)

	def add_to_history(self, music):
		self.__music_history.add_music(music)
	
	def is_online(self):
		return self.__audio_scrobbler_service.logged
	
	def audio_scrobbler_now_playing(self, music):
		if self.is_online():
			self.__audio_scrobbler_service.now_playing(music)
	
	def start(self):
		self.__applock.wait()
	
	def check_selected_directory(self):
		if not self.selected_directory:
			appuifw.note(u"It's necessary to select a directory first", "info")
			return False
		
		return True

	def show_message(self, message):
		appuifw.note(unicode(message), "info")
	
	def close(self):
		appuifw.app.menu = []
		appuifw.app.body = None
		appuifw.app.exit_key_handler = None


class SelectorPath:
	def __init__(self):
		self.drivelist = e32.drive_list()
		self.current_directory = None
	
	def pop(self):
		if not self.current_directory:
			return

		up_dir = os.path.split(self.current_directory)[0]
		if up_dir != self.current_directory:
			self.current_directory = up_dir
		else:
			self.current_directory = None
			
	def get(self, idx):
		if self.current_directory:
			if len(self.dirlist) > 0:
				ret = os.path.join(self.current_directory, self.dirlist[idx])
			else:
				ret = self.current_directory
		else:
			ret = self.dirlist[idx] + os.sep
		
		return ret
		
	def cd(self, idx):
		self.current_directory = self.get(idx)

	def get_list(self):
		self.dirlist = None
		
		if not self.current_directory:
			entries = self.drivelist
			self.dirlist = self.drivelist
		else:
			is_dir = lambda n: os.path.isdir(os.path.join(self.current_directory, n))
			self.dirlist = map(unicode, filter(is_dir, os.listdir(self.current_directory)))

			entries = self.dirlist
						
		return entries

	def get_current_dir(self):
		return self.current_directory

class DirectorySelector:
	def __init__(self, select_action):
		self.path = SelectorPath()
		self.select_action = select_action
		self.lb = None

	def init(self):
		self.path = SelectorPath()
		self.lb = None

	def run(self):
		from key_codes import EKeyLeftArrow, EKeyRightArrow, EKeySelect 
		
		entries = self.path.get_list()
		
		self.lb = appuifw.Listbox(entries, self.lbox_observe)
		self.lb.bind(EKeyRightArrow, lambda: self.lbox_observe())
		self.lb.bind(EKeySelect, lambda: self.select_dir())
		self.lb.bind(EKeyLeftArrow, lambda: self.move_up())
		
		self.lb.set_list(entries)

		return self.lb

	def move_up(self):
		self.path.pop()
		entries = self.path.get_list()
		self.lb.set_list(entries)

	def select_dir(self):
		self.lbox_observe()
		selected = self.path.get_current_dir()
		self.select_action(selected)

	def lbox_observe(self):
		index = self.lb.current()

		selected = self.path.get(index)
		self.path.cd(index)

		entries = self.path.get_list()
		if entries:
			self.lb.set_list(entries)

class AccessPointServices(object):
	def __init__(self, access_point_file_path="e:\\apid.txt"):
		self.ap_file_path = access_point_file_path
	
	def unset_accesspoint(self):
		f = open(self.ap_file_path, "w")
		f.write(repr(None))
		f.close()
		appuifw.note(u"Default access point is unset ", "info")

	def select_accesspoint(self):
		apid = socket.select_access_point()
		if appuifw.query(u"Set as default?", "query") == True:
			f = open(self.ap_file_path, "w")
			f.write(repr(apid))
			f.close()
			appuifw.note(u"Saved default access point ", "info")
		apo = socket.access_point(apid)
		socket.set_default_access_point(apo)

	def set_accesspoint(self):
		try:
			f = open(self.ap_file_path, "rb")
			setting = f.read()
			apid = eval(setting)
			f.close()
			if not apid == None:
				apo = socket.access_point(apid)
				socket.set_default_access_point(apo)
			else:
				self.select_accesspoint()
		except:
			self.select_accesspoint()


if __name__ == u"__main__":
	db_helper = DbHelper("c:\\data\\kenobi_player\\history.db")

	history_repository = MusicHistoryRepository(db_helper)
	user_repository = AudioScrobblerUserRepository(db_helper)

	as_service = AudioScrobblerService("doug_fernando", "sko445")	
	history = MusicHistory(history_repository, as_service)
	
	ui = PlayerUI(MusicsFactory(), history, as_service)

	try:
		ui.start()
	finally:
		ui.close()
		print "bye" 
