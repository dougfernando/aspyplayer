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
from key_codes import EKeyLeftArrow, EKeyRightArrow, EKeySelect 

import appuifw
import audio
import e32
import e32db
import md5
import os
import time
import urllib
import socket

##########################################################
######################### MODELS 

class MusicsFactory(object):
	def __init__(self, file_system_services):
		self.__fs_services = file_system_services
		
	def load_all_musics(self, root_path):
		result = []
		files = self.__fs_services.find_all_files(root_path, ".mp3")
		for file in files:
			result.append(Music(file))
		
		return result


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
		self.now_playing_sent = False
	
	def init_music(self):
		if self.file_path:
			path = self.file_path
			fp = open(path, "r")
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

	def get_player_position_in_seconds(self):
		return int(self.player.current_position() / 1e6)

	def can_update_position(self):
		curr_pos = self.get_player_position_in_seconds()
		if self.position != curr_pos:
			self.position = curr_pos
			return True
	
		return False

	def can_be_added_to_history(self):
		player_curr_pos = self.get_player_position_in_seconds()
		min_length_cond = player_curr_pos > 30
		min_length_played_cond = (player_curr_pos > 240 or (
				float(player_curr_pos) / self.length) > 0.5)
		
		return min_length_cond and min_length_played_cond

	def current_position_formatted(self):
		return self.format_secs_to_str(self.position)
	
	def length_formatted(self):
		return self.format_secs_to_str(self.length)
	
	def format_secs_to_str(self, seconds):
		hours = seconds / 3600
		seconds_remaining = seconds % 3600
		minutes = seconds_remaining / 60
		
		seconds = seconds % 60

		if hours >= 1:
			return unicode("%02i:%02i:%02i" % (hours, minutes, seconds))
		else:
			return unicode("%02i:%02i" % (minutes, seconds))
	
	def get_status_formatted(self):
		if self.is_playing():
			return "Playing"
		
		return "Stopped" 

class MusicPlayer(object):
	current_volume = -1

	def __init__(self, music, player=None):
		self.__music = music
		self.__paused = False
		self.loaded = False
		self.__player = player
		self.__current_position = None
		self.volume_step = 1
	
	def play(self, callback=None):
		if not self.__paused:
			self.__player = audio.Sound.open(self.__music.file_path)
			self.configure_volume()
			self.__music.length = int(self.__player.duration() / 1e6)
			self.__music.played_at = int(time.time())
			self.loaded = True
		else:
			self.__player.set_position(self.__current_position)
		
		self.__player.play(times=1, interval=0, callback=callback)

	def configure_volume(self):
		# HACK: I don't know why, but using directly the class attribute does not work
		volume = self.__class__.current_volume 
		if volume < 0: # default value = -1
			default_volume = self.__player.max_volume() / 4
			self.__class__.current_volume = default_volume

		self.volume_step = self.__player.max_volume() / 10 # TODO: maybe it can be a constant
		self.__player.set_volume(self.__class__.current_volume)
		
	def stop(self):
		if self.loaded:
			self.__player.stop()
			self.__player.close()
			self.loaded = False
	
	def pause(self):
		if self.loaded:
			self.__current_position = player.current_position()
			self.__player.stop()
			self.__paused = True

	def volume_up(self):
		if self.loaded:
			self.__class__.current_volume = self.__class__.current_volume + self.volume_step
			if self.__class__.current_volume > self.__player.max_volume(): 
				self.__class__.current_volume = self.__player.max_volume()
			
			self.__player.set_volume(self.__class__.current_volume)
	
	def volume_down(self):
		if self.loaded:
			self.__class__.current_volume = self.__class__.current_volume - self.volume_step
			if self.__class__.current_volume < 0:
				self.__class__.current_volume = 0
			
			self.__player.set_volume(self.__class__.current_volume)

	def is_playing(self):
		return self.__player.state() == 2

	def current_volume_percentage(self):
		return int((float(self.__class__.current_volume) / self.__player.max_volume()) * 100)
	
	def current_position(self):
		return self.__player.current_position()


# FIXME: This class has a bad name, it must be renamed	
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
	
	def is_empty(self):
		return len(self.__musics) < 1
	
	def play(self):
		self.__should_stop = False
		
		while self.current_music != None:
			self.current_music.play(self.play_callback)
			self.__listener.update_music(self.current_music)

			self.play_current_music()
				
			if self.__should_stop: break
			if not self.move_next(): break
			
			self.__timer.after(0.3)
	
	def play_current_music(self):
		added_to_history = False;
		while self.current_music.is_playing():
			if not added_to_history:
				if self.current_music.can_be_added_to_history():
					self.__listener.add_to_history(self.current_music)
					added_to_history = True
			
			if self.current_music.can_update_position():
				self.__listener.update_music(self.current_music)
			
			e32.ao_yield()

		self.__listener.finished_music(self.current_music)

	
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
			self.current_music = self.__musics[self.__current_index]
			return True
	
		return False
	
	def move_previous(self):
		if self.__current_index > 0:
			self.__current_index = self.__current_index - 1
			self.current_music = self.__musics[self.__current_index]
			return True
		
		return False

	def current_position_formated(self):
		return unicode("%i / %i" % (self.__current_index + 1, len(self.__musics)))


class MusicHistory(object):
	def __init__(self, repository, audio_scrobbler_service):
		self.__batch_size = 50
		self.__repository = repository
		self.__audio_scrobbler_service = audio_scrobbler_service

	def add_music(self, music):
		self.__repository.save_music(music)
	
	def clear(self):
		self.__repository.clear_history()
	
	def send_to_audioscrobbler(self):
		musics = self.__repository.load_all_history()
		if musics and len(musics) < self.__batch_size:
			self.__audio_scrobbler_service.send(musics)
			self.clear()
		elif musics:
			self.send_batches_to_audioscrobbler(musics)

	def send_batches_to_audioscrobbler(self, musics):
		assert len(musics) >= self.__batch_size
		
		num_full_batches = len(musics) / self.__batch_size
		for i in range(num_full_batches):
			start = i * self.__batch_size
			end = start + self.__batch_size
			batch = musics[start:end]
			self.send_batch(batch)
		
		remainings = len(musics) % self.__batch_size
		if remainings > 0:
			batch = musics[len(musics)-remainings:len(musics)]
			self.send_batch(batch)
		
	def send_batch(self, musics_batch):
		self.__audio_scrobbler_service.send(musics_batch)
		self.__repository.remove_musics(musics_batch)


class AudioScrobblerUser(object):
	def __init__(self, username, password, hashed=False):
		self.username = username
		if not hashed:
			self.password = md5.md5(password).hexdigest()
		else:
			self.password = password

##########################################################
######################### REPOSITORIES 

class MusicRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper
	
	def count_all(self):
		cmd = "SELECT Path FROM Music"
		rows = self.__db_helper.execute_reader(cmd)
		return len(rows)
	
	def count_all_artists(self):
		return len(self.find_all_artists())
	
	def count_all_albums(self):
		return len(self.find_all_albums())
	
	def find_all(self):
		cmd = "SELECT Path FROM Music"
		rows = self.__db_helper.self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return result
	
	def find_all_artists(self):
		cmd = "SELECT Artist FROM Music"
		rows = self.__db_helper.self.__db_helper.execute_reader(cmd)
		result = [row[0] for row in rows]
		return result

	def find_all_albums(self):
		cmd = "SELECT Album FROM Music"
		rows = self.__db_helper.self.__db_helper.execute_reader(cmd)
		result = [row[0] for row in rows]
		return result

	def find_all_by_artist(self, artist):
		cmd = "SELECT Path FROM Music WHERE Artist = '%s'" % artist.replace("'", "''")
		rows = self.__db_helper.self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return result

	def find_all_by_album(self, album):
		cmd = "SELECT Path FROM Music WHERE Album = '%s'" % artist.replace("'", "''")
		rows = self.__db_helper.self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return result

	def save(self, music):
		cmd = "INSERT INTO Music (Path, Artist, Album) VALUES('%s', '%s', '%s')" % (music.file_path.replace("'", "''"),
								music.artist.replace("'", "''"), music.album.replace("'", "''"))
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def delete(self, music_path):
		cmd = "DELETE FROM Music WHERE Path = '%s'" % music_path
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def update_library(self, musics_path):
		all_music_in_db = self.find_all()
		all_music_in_db_path = [music.file_path for music in all_music_in_db]
		input_set, db_set = set(musics_path), set(all_music_in_db_path)
		to_be_added = input_set.intersection(db_set)
		to_be_deleted = db_set.intersection(db_set)

		new_musics = [Music(path) for path in to_be_added]
		for music in new_musics:
			self.save(music) 
	
		for music_path in to_be_deleted:
			self.delete(music_path)


class AudioScrobblerUserRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper

	def load(self):
		cmd = "SELECT UserName, Password FROM User"
		rows = self.__db_helper.execute_reader(cmd)
		if rows:
			return AudioScrobblerUser(rows[0][0], rows[0][1], True)
		
		return None
	
	def save(self, user):
		remove_cmd = "DELETE FROM USER"
		insert_cmd = "INSERT INTO User (UserName, Password) VALUES('%s', '%s')" % (user.username.replace("'", "''"), user.password.replace("'", "''"))

		result = self.__db_helper.execute_nonquery(remove_cmd)
		result = self.__db_helper.execute_nonquery(insert_cmd)
		assert result > 0
	

class MusicHistoryRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper
	
	def save_music(self, music):
		cmd = "INSERT INTO Music_History (Artist, Track, PlayedAt, Album, TrackLength) VALUES('%s', '%s', %i, '%s', %i)" % \
				(music.artist.replace("'", "''"), music.title.replace("'", "''"), 
					music.played_at, music.album.replace("'", "''"), music.length)
		
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def remove_musics(self, musics):
		for music in musics:
			cmd = "DELETE FROM Music_History WHERE PlayedAt = %i" % (music.played_at)
			self.__db_helper.execute_nonquery(cmd)
	
	def clear_history(self):
		cmd = "DELETE FROM Music_History"
		self.__db_helper.execute_nonquery(cmd)
	
	def load_all_history(self):
		cmd = "SELECT Artist, Track, PlayedAt, Album, TrackLength FROM Music_History"
		rows = self.__db_helper.execute_reader(cmd)
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


##########################################################
######################### SERVICES 


class AudioScrobblerError(Exception):
	pass

class AudioScrobblerCredentialsError(Exception):
	pass

class NoAudioScrobblerUserError(Exception):
	pass

class AudioScrobblerService(object):
	def __init__(self, user_repository): 
		self.logged = False
		self.__user_repository = user_repository
		self.__handshake_url = "http://post.audioscrobbler.com/"
		self.__handshake_data = None
		self.__session_id = None
		self.__now_url = None
		self.__post_url = None
	
	def set_credentials(self, user):
		self.__user_repository.save(user)
		
	def create_handshake_data(self):
		user = self.__user_repository.load()
		if not user:
			raise NoAudioScrobblerUserError("You must set an user/password first")
		
		client_id = "tst"
		client_version = "1.0"
		tstamp = int(time.time())
		token  = md5.md5("%s%d" % (user.password, tstamp)).hexdigest()
   		
   		values = {
			"hs": "true", 
			"p": '1.2', 
			"c": client_id, 
			"v": client_version, 
			"u": user.username, 
			"t": tstamp, 
			"a": token
	 	}
   		
   		self.__handshake_data = urllib.urlencode(values)
   		print self.__handshake_data

	# TODO: consider the time to retry if failed
	def login(self):
		self.create_handshake_data()
		response = urllib.urlopen("%s?%s" % (self.__handshake_url, self.__handshake_data))
		self.__session_id, 
		self.__now_url,  
		self.__post_url = self.handle_handshake_response(response)
		self.logged = True
		
		print "%s %s %s" % (self.__session_id, self.__now_url, self.__post_url)
	
	def handle_handshake_response(self, response):
		result = response.read()
		lines = result.split("\n")

		if lines[0] == "OK":
			return (lines[1], lines[2], lines[3])
		else:
			self.handle_handshake_error(lines[0])
		
	def handle_handshake_error(self, error):
		if error == "BADAUTH":
			raise AudioScrobblerCredentialsError("Bad username/password")
		elif error == "BANNED":
			raise AudioScrobblerError("'This client-version was banned by Audioscrobbler. Please contact the author of this module!'")
		elif error == "BADTIME":
			raise AudioScrobblerError("'Your system time is out of sync with Audioscrobbler. Consider using an NTP-client to keep you system time in sync.'")
		elif error.startswith("FAILED"):
	  		raise AudioScrobblerError("Authentication with AS failed. Reason: %s" % error)
		else:
			raise AudioScrobblerError("Authentication with AS failed.")
	
	def check_login(self):
		if not self.logged:
			raise AudioScrobblerError("You must be logged to execute this operation")
		
	def now_playing(self, music):
		if music.now_playing_sent: return
		
		self.check_login()
		
		values = {
			"s": self.__session_id, 
			"a": unicode(music.artist).encode("utf-8"), 
			"t": unicode(music.title).encode("utf-8"), 
			"b": unicode(music.album).encode("utf-8"), 
			"l": music.length, 
			"n": music.number, 
			"m": music.music_brainz_ID
		}

		data = urllib.urlencode(values)
		response = urllib.urlopen(self.__now_url, data)
		result = response.read()
	
		if result.strip() == "OK":
			print 'Sent Now Playing %s' % (music.title)
			music.now_playing_sent = True
			return True
		elif result.strip() == "BADSESSION":
			raise AudioScrobblerError("Invalid session")
		else:
			return False
	
	def send(self, musics):
		self.check_login()
		
		data = self.create_send_music_data(musics)
		response = urllib.urlopen(self.__post_url, data)
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
			
		values["s"] = self.__session_id

		data = urllib.urlencode(values)
		
		return data


##########################################################
######################### INFRASTRUCTURE 

class FileSystemServices:
	# TODO: Bug Unicode error for strange files name, e.g, containing "è"
	def find_all_files(self, root_dir, file_extension):
		result = []
		predicate = lambda f: f.endswith(file_extension)
		
		def walk(arg, dirname, names):
			files_filtered = filter(predicate, names)
			
			for file in files_filtered:
				full_file_path = "%s\\%s" %(dirname, file.decode('utf-8'))
				result.append(full_file_path)
		
		os.path.walk(root_dir, walk, None)
		
		return result

	def exists(self, path):
		return os.path.exists(path)

	def get_base_directory(self, path):
		return os.path.split(path)
	
	def base_directory_exists(self, full_path):
		base_dir = self.get_base_directory(full_path)
		return self.exists(base_dir)

	def is_directory(self, full_path):
		return os.path.isdir(full_path)
	
	def join(self, directory, file):
		return os.path.join(directory, file)
	
	def get_directory_files(self, directory_path):
		return os.listdir(directory_path)

	def create_base_directories_for(self, full_path):
		db_dir = os.path.split(self.__db_path)[0]
		if not os.path.exists(db_dir):
			os.makedirs(db_dir)


class DirectoryNavigatorContent:
	def __init__(self):
		self.__drivelist = [u"C:", u"E:"]
		self.__current_directory = None
		self.__dir_list = None
		self.__fs_services = FileSystemServices()
	
	def move_up(self):
		if not self.__current_directory:
			return

		up_dir = self.__fs_services.get_base_directory(self.__current_directory)[0]
		if up_dir != self.__current_directory:
			self.__current_directory = up_dir
		else:
			self.__current_directory = None
			
	def move_down(self, idx):
		if self.__current_directory:
			if len(self.__dir_list) > 0:
				ret = self.__fs_services.join(self.__current_directory, self.__dir_list[idx])
			else:
				ret = self.__current_directory
		else:
			ret = self.__dir_list[idx] + os.sep
		
		return ret
		
	def change_dir(self, idx):
		self.__current_directory = self.move_down(idx)

	def get_list(self):
		self.__dir_list = None
		
		if not self.__current_directory:
			entries = self.__drivelist
			self.__dir_list = self.__drivelist
		else:
			is_dir = lambda n: self.__fs_services.is_directory(self.__fs_services.join(self.__current_directory, n))
			full_directory_content = self.__fs_services.get_directory_files(self.__current_directory)
			self.__dir_list = map(unicode, filter(is_dir, full_directory_content))

			entries = self.__dir_list
						
		return entries

	def get_current_dir(self):
		return self.__current_directory


class DbHelper(object):
	def __init__(self, dbpath, file_system_services):
		self.__db_path = dbpath
		self.__fs_services = file_system_services
		db_already_exists = self.__fs_services.exists(self.__db_path) 
		
		self.db = e32db.Dbms()
		self.dbv = e32db.Db_view()
		
		if db_already_exists:
			self.db.open(unicode(dbpath))
		else:
			self.check_db_directory()
			self.db.create(unicode(dbpath))
			self.db.open(unicode(dbpath))
			self.create_tables()

	def close(self):
		self.db.close()

	def check_db_directory(self):
		self.__fs_services.create_base_directories_for(self.__db_path)

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
		self.create_music_table()
	
	def create_music_table(self):
		cmd = "CREATE TABLE Music (Path varchar(256), Artist varchar(200), Album varchar(200))"
		self.execute_nonquery(cmd)
	
	def create_music_history_table(self):
		cmd = "CREATE TABLE Music_History (Artist varchar(200), Track varchar(200), PlayedAt integer, Album varchar(200), TrackLength integer)"
		self.execute_nonquery(cmd)

	def create_user_table(self):
		cmd = "CREATE TABLE User (UserName varchar(200), Password varchar(200))"
		self.execute_nonquery(cmd)


##########################################################
######################### USER INTERFACE 

class PlayerUI(object):
	def __init__(self, service_locator):
		self.presenter = PlayerUIPresenter(self, service_locator)
		self.navigator = ScreenNavigator(self, service_locator)
		
		self.__ap_services = AccessPointServices(self)
		self.__applock = e32.Ao_lock()
		
		self.config_events()
		
		self.__default_font = None
		self.__default_body = None
		self.__is_selecting_directory = False
		self.__directory_selector = DirectorySelector(lambda dir: self.set_selected_directory(dir))
		self.selected_directory = None
		
		self.navigator.go_to_main_window()
		
#		self.basic_config()
#		self.init_menus()
#		self.init_background()
		
	
	def basic_config(self):
		appuifw.app.screen = "normal"
		appuifw.app.title = u"Audioscrobbler PyS60 Player"
	
	def init_menus(self):
		appuifw.app.menu = [
			(u"Select the Music DIR", self.select_directory), 
			(u"Controls", (
				(u"Play", self.presenter.play),
				(u"Stop", self.presenter.stop), 
				(u"Next", self.presenter.next),
				(u"Previous", self.presenter.previous))), 
			(u"Volume", 
				((u"Up", self.presenter.volume_up), (u"Down", self.presenter.volume_down))), 
			(u"Last.fm", (
				(u"Connect", self.presenter.connect), 
				(u"Clear History", self.presenter.clear_as_db), 
				(u"Submit History", self.presenter.send_history),
				(u"Set Credentials", self.presenter.create_as_credentials))),
			(u"Tests", self.test),
			(u"About", self.about), 
			(u"Exit", self.quit)]

	def about(self):
		self.show_message("AsPy Player\nCreated by Douglas\n(doug.fernando at gmail)\n\ncode.google.com/p/aspyplayer")
		
	def test(self):
		if self.ask("This functionality is for testing only. It may crach the application. Continue?"):
			Fixtures().run()
	
	def init_background(self):
		self.render_initial_screen()

	def render_initial_screen(self):
		t = appuifw.Text()
		appuifw.app.body = t
		self.__default_font = t.font
		t.color = (255, 0, 0)
		t.style = appuifw.STYLE_BOLD
		t.add(u"\n  Audioscrobbler pyS60 player\n\n\n")
		t.color = 0
		t.style = appuifw.STYLE_ITALIC | appuifw.STYLE_BOLD 
		t.add(u" Using the 'options' menu, select a directory with the musics to be played\n\n\n")
		t.font = u"albi9b"
		t.add(u"web site:\n    http://code.google.com/p/aspyplayer/")

	def config_events(self):
		appuifw.app.exit_key_handler = self.quit
	
	def quit(self):
		if self.ask("Are you sure you want to exit the application?"):
			try:
				self.presenter.stop()
			finally:
				self.__applock.signal()
	
	def set_accesspoint(self):
		self.__ap_services.set_accesspoint()

	def show_message(self, message):
		appuifw.note(unicode(message), "info")

	def close(self):
		appuifw.app.menu = []
		appuifw.app.body = None
		appuifw.app.exit_key_handler = None

	def show_error_message(self, message):
		appuifw.note(unicode(message), "error")

	def ask_text(self, info):
		return appuifw.query(unicode(info), "text")

	def ask_password(self, info):
		return appuifw.query(unicode(info), "code")

	def ask(self, question):
		return appuifw.query(unicode(question), "query")

	def select_directory(self): 
		self.__default_body = (appuifw.app.body, appuifw.app.menu) 
		self.__directory_selector.init()
		lb = self.__directory_selector.run()
		self.__is_selecting_directory = True
		appuifw.app.body = lb
		appuifw.app.menu = [(u"Select", self.__directory_selector.select_dir),
							(u"Cancel", self.cancel_select_directory)]

	def cancel_select_directory(self):
		appuifw.app.body, appuifw.app.menu = self.__default_body
		self.__is_selecting_directory = False
		if not self.presenter.is_in_play_mode():
			self.render_initial_screen()

	def set_selected_directory(self, dir=None):
		if dir:
			self.selected_directory = dir

		appuifw.app.body, appuifw.app.menu = self.__default_body
		self.__is_selecting_directory = False
		self.presenter.update_directory()
	
	def update_music(self, music):
		if not self.__is_selecting_directory:
			self.show_music_information(music)
			self.presenter.audio_scrobbler_now_playing(music)

	def show_music_information(self, music):
		t = appuifw.app.body 
		t.set(u"")
		t.font = self.__default_font
		t.color = (255, 0, 0)
		t.style = appuifw.STYLE_BOLD
		t.add(u"Current:\n\n")
		t.color = 0
		t.style = appuifw.STYLE_ITALIC | appuifw.STYLE_BOLD 
		t.add(unicode("  Artist: %s\n" % music.artist))
		t.add(unicode("  Track: %s\n\n" % music.title))
		t.font = u"albi10b"
		t.add(unicode("  Status: %s\n\n" % music.get_status_formatted()))		
		t.add(unicode("  %s - %s\n\n" % (music.current_position_formatted(), music.length_formatted())))
		t.font = u"albi9b"
		t.add(unicode("  %s" % self.presenter.get_current_list_position()))

	def start(self):
		self.__applock.wait()


class ScreenNavigator(object):
	def __init__(self, player_ui, service_locator):
		self.__player_ui = player_ui
		self.__service_locator = service_locator
		self.__main_window = MainWindow(self.__player_ui, self, self.__service_locator.music_repository, self.__service_locator.file_system_services)
		self.__select_window = SelectWindow(self.__player_ui, self, self.__service_locator.music_repository)
		self.__all_musics_window = AllMusicsWindow(self.__player_ui, self, self.__service_locator.music_repository)
		self.__artists_window = ArtistsWindow(self.__player_ui, self, self.__service_locator.music_repository)
		self.__albums_window = AlbumsWindow(self.__player_ui, self, self.__service_locator.music_repository)
		self.__musics_window = MusicsWindow(self.__player_ui, self)
	
	def go_to_main_window(self):
		self.go_to(self.__main_window)

	def go_to_select_window(self):
		self.go_to(self.__select_window)

	def go_to_all_musics_window(self):
		self.go_to(self.__all_musics_window)

	def go_to_artists_window(self):
		self.go_to(self.__artists_window)

	def go_to_albums_window(self):
		self.go_to(self.__albums_window)

	def go_to_musics(self, musics):
		self.__musics_window.musics = musics
		self.go_to(self.__musics_window)

	def go_to(self, window):
		appuifw.app.body = window.body
		appuifw.app.menu = window.menu
		appuifw.app.title = window.title
		window.show()


class Window(object):
	def __init__(self, player_ui, navigator, title="Audioscrobbler PyS60 Player"):
		self.player_ui = player_ui
		self.navigator = navigator
		self.title = unicode(title)
		self.body = None
		self.menu = []

	def about(self):
		self.player_ui.show_message("AsPy Player\nCreated by Douglas\n(doug.fernando at gmail)\n\ncode.google.com/p/aspyplayer")

	def set_menu(self, menu):
		pass

	def show(self):
		appuifw.app.screen = "normal"
		appuifw.app.exit_key_handler = self.player_ui.quit


class MainWindow(Window):
	def __init__(self, player_ui, navigator, music_repository, file_system_services):
		Window.__init__(self, player_ui, navigator)
		self.__fs_services = file_system_services
		self.__music_repository = music_repository
		self.body = appuifw.Listbox(self.get_list_items(), self.go_to)
		self.menu = self.get_menu_items()
	
	def go_to(self):
		index = self.body.current()
		if index == 0:
			self.navigator.go_to_select_window()
		else:
			self.about()
	
	def get_list_items(self):
		items = [(u"Your Music", unicode("%i musics" % self.__music_repository.count_all())), 
				(u"About", u"code.google.com/p/aspyplayer/")]
		return items
	
	def update_music_library(self):
		all_musics_in_c = self.__fs_services.find_all_files("C:\\", ".mp3")
		all_musics_in_e = self.__fs_services.find_all_files("E:\\", ".mp3")
		all_music = []
		all_music.extend(all_musics_in_c, all_musics_in_e)
		self.__music_repository.update_library(all_music)
		self.player_ui.show_message("Library updated")
	
	def get_menu_items(self):
		return [
			(u"Update Musics Library", self.update_music_library),
			(u"About", self.about), 
			(u"Exit", self.player_ui.quit)]
	

class SelectWindow(Window):
	def __init__(self, player_ui, navigator, music_repository):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = music_repository
		self.body = appuifw.Listbox(self.get_list_items(), self.go_to)
		self.menu = self.get_menu_items()

	def get_list_items(self):
		items = [(u"All Music", unicode("%i musics" % self.__music_repository.count_all())), 
				(u"Artists", u"%i artists" % self.__music_repository.count_all_artists()),
				(u"Albums", u"%i albums" % self.__music_repository.count_all_albums())]
		return items
	
	def get_menu_items(self):
		return [
			(u"Voltar", self.navigator.go_to_main_window),
			(u"About", self.about), 
			(u"Exit", self.player_ui.quit)]

	def go_to(self):
		index = self.body.current()
		if index == 0:
			self.navigator.go_to_all_musics_window()
		elif index == 1:
			self.navigator.go_to_artists_window()
		else:
			self.navigator.go_to_albums_window()

	def show(self):
		appuifw.app.exit_key_handler = self.navigator.go_to_main_window


class MusicsWindow(Window):
	def __init__(self, player_ui, navigator, title=""):
		if title: 
			Window.__init__(self, player_ui, navigator, title)
		else:
			Window.__init__(self, player_ui, navigator)
		self.body = appuifw.Listbox(self.get_list_items(), self.go_to)
		self.menu = self.get_menu_items()
		self.musics = []

	def get_list_items(self):
		items = [u"empty"]
		return items
	
	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		return [
			(u"Voltar", self.back),
			(u"About", self.about), 
			(u"Exit", self.player_ui.quit)]

	def go_to(self):
		pass

	def show(self):
		list_items = []
		for music in self.musics:
			list_items.append(unicode(music.title))
		
		self.body.set_list(list_items)
		
		appuifw.app.exit_key_handler = self.back

class AllMusicsWindow(MusicsWindow):
	def __init__(self, player_ui, navigator, music_repository):
		MusicsWindow.__init__(self, player_ui, navigator)
		self.musics = music_repository.find_all() # atualizado no update da library
	

class ArtistsWindow(Window):
	def __init__(self, player_ui, navigator, music_repository):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = music_repository
		self.artists = map(unicode, self.__music_repository.find_all_artists())
		self.body = appuifw.Listbox(self.artists, self.go_to)
		self.menu = self.get_menu_items()

	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		return [
			(u"Voltar", self.back),
			(u"About", self.about), 
			(u"Exit", self.player_ui.quit)]

	def go_to(self):
		index = self.body.current()
		artist_selected = self.artists[index]
		musics = self.__music_repository.find_all_by_artist(artist_selected)
		self.navigator.go_to_musics(musics)

	def show(self):
		appuifw.app.exit_key_handler = self.back


class AlbumsWindow(Window):
	def __init__(self, player_ui, navigator, music_repository):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = music_repository
		self.albums = map(unicode, self.__music_repository.find_all_albums())
		self.body = appuifw.Listbox(self.albums, self.go_to)
		self.menu = self.get_menu_items()

	def get_list_items(self):
		items = [(u"All Music", unicode("%i musics" % self.__music_repository.count_all())), 
				(u"Artists", u"%i artists" % self.__music_repository.count_all_artists()),
				(u"Albums", u"%i albums" % self.__music_repository.count_all_albums())]
		return items
	
	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		return [
			(u"Voltar", self.back),
			(u"About", self.about), 
			(u"Exit", self.player_ui.quit)]

	def go_to(self):
		index = self.body.current()
		album_selected = self.albums[index]
		musics = self.__music_repository.find_all_by_album(album_selected)
		self.navigator.go_to_musics(musics)

	def show(self):
		appuifw.app.exit_key_handler = self.back


class PlayerUIPresenter(object):
	def __init__(self, view, service_locator):
		self.view = view
		self.__music_factory = service_locator.music_factory
		self.__music_history = service_locator.music_history
		self.__audio_scrobbler_service = service_locator.as_service
		self.music_list = None

	def update_directory(self):
		if self.music_list:
			self.music_list.stop()
		
		self.music_list = MusicList(self.__music_factory, self.view.selected_directory, self)
		if not self.music_list.is_empty():
			self.play()
		else:
			self.view.show_message("No musics in the selected directory")
			self.view.render_initial_screen()
			self.music_list = None

	def is_in_play_mode(self):
		return self.music_list

	def clear_as_db(self):
		if self.view.ask("Are you sure you want to clear your history?"):
			self.__music_history.clear()
	
	def connect(self):
		if not self.is_online():
			self.view.set_accesspoint()

			try:
				return self.try_login()
			except NoAudioScrobblerUserError:
				self.create_as_credentials()
				return self.try_login()
			
			return False
		else:
			self.view.show_message("Already connected!")
	
	def try_login(self):
		login = lambda: self.__audio_scrobbler_service.login()
		try:
			self.long_operation(login)
			return True
		except AudioScrobblerCredentialsError:
			self.view.show_error_message("Bad Username/Password. Change your credentials")

		return False
	
	def create_as_credentials(self):
		user_name = self.view.ask_text("Inform your username")
		if not user_name: return
		
		password = self.view.ask_password("Inform your password")
		if not password: return
		
		self.__audio_scrobbler_service.set_credentials(AudioScrobblerUser(user_name, password))
		
		self.view.show_message("Credentials saved")
		
	def send_history(self):
		if not self.is_online():
			if not self.connect():
				self.show_cannot_connect()

		self.__music_history.send_to_audioscrobbler()
	
	def show_cannot_connect(self):
		self.view.show_error_message("It was not possible to connect!")
	
	def play(self): 
		if self.check_selected_directory():
			self.music_list.play()

	def pause(self): 
		if self.music_list:
			self.music_list.play()
	
	def long_operation(self, operation):
		operation()
	
	def stop(self):
		if self.music_list:	
			self.music_list.stop()
			self.update_music(self.music_list.current_music)
			
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
		self.view.show_message("Current_volume: %s" % (
						self.music_list.current_music.player.current_volume_percentage()))
		
	def volume_down(self):
		if self.music_list:	
			self.music_list.current_music.volume_down()
			self.show_current_volume()
		
	def finished_music(self, music):
		if self.is_online():
			self.__music_history.send_to_audioscrobbler()
	
	def update_music(self, music):
		self.view.update_music(music)
	
	def add_to_history(self, music):
		self.__music_history.add_music(music)
	
	def is_online(self):
		return self.__audio_scrobbler_service.logged
	
	def audio_scrobbler_now_playing(self, music):
		if self.is_online():
			self.__audio_scrobbler_service.now_playing(music)
	
	def check_selected_directory(self):
		if not self.view.selected_directory:
			self.view.show_message("It's necessary to select a directory first")
			return False
		
		return True

	def get_current_list_position(self):
		return self.music_list.current_position_formated()


class DirectorySelector:
	def __init__(self, select_action):
		self.__navigator = DirectoryNavigatorContent()
		self.__select_action = select_action
		self.__list_box = None

	def init(self):
		self.__navigator = DirectoryNavigatorContent()
		self.__list_box = None

	def run(self):
		entries = self.__navigator.get_list()
		
		self.__list_box = appuifw.Listbox(entries, self.move_down)
		self.__list_box.bind(EKeyRightArrow, lambda: self.move_down())
		self.__list_box.bind(EKeySelect, lambda: self.move_down())
		self.__list_box.bind(EKeyLeftArrow, lambda: self.move_up())
		
		self.__list_box.set_list(entries)

		return self.__list_box

	def move_up(self):
		self.__navigator.move_up()
		entries = self.__navigator.get_list()
		self.__list_box.set_list(entries)

	def select_dir(self):
		self.move_down()
		selected = self.__navigator.get_current_dir()
		self.__select_action(selected)

	def move_down(self):
		index = self.__list_box.current()

		selected = self.__navigator.move_down(index)
		self.__navigator.change_dir(index)

		entries = self.__navigator.get_list()
		if entries:
			self.__list_box.set_list(entries)


# TODO: remove the hardcoded file path
class AccessPointServices(object):
	def __init__(self, view, access_point_file_path="e:\\apid.txt"):
		self.__view = view
		self.__ap_file_path = access_point_file_path
	
	def unset_accesspoint(self):
		f = open(self.__ap_file_path, "w")
		f.write(repr(None))
		f.close()
		self.__view.show_message("Default access point is unset ")

	def select_accesspoint(self):
		apid = socket.select_access_point()
		if self.__view.ask("Set as default?") == True:
			f = open(self.__ap_file_path, "w")
			f.write(repr(apid))
			f.close()
			self.__view.show_message("Saved default access point")
		
		apo = socket.access_point(apid)
		socket.set_default_access_point(apo)

	def set_accesspoint(self):
		try:
			f = open(self.__ap_file_path, "rb")
			setting = f.read()
			apid = eval(setting)
			f.close()
			if apid:
				apo = socket.access_point(apid)
				socket.set_default_access_point(apo)
			else:
				self.select_accesspoint()
		except:
			self.select_accesspoint()


class ServiceLocator(object):
	def __init__(self):
		self.file_system_services = FileSystemServices()
		self.db_helper = DbHelper("c:\\data\\aspyplayer\\aspyplayer.db", self.file_system_services)
		self.history_repository = MusicHistoryRepository(self.db_helper)
		self.user_repository = AudioScrobblerUserRepository(self.db_helper)
		self.as_service = AudioScrobblerService(self.user_repository)	
		self.music_history = MusicHistory(self.history_repository, self.as_service)
		self.music_factory = MusicsFactory(self.file_system_services)
		self.music_repository = MusicRepository(self.db_helper)

	def close(self):
		self.file_system_services = None
		self.db_helper.close()
		self.db_helper = None
		self.history_repository = None
		self.user_repository = None
		self.as_service = None	
		self.music_history = None
		self.music_factory = None


##########################################################
######################### TESTING 

class Fixture(object):
	def assertEquals(self, expected, result, description):
		if expected != result:
			print "expected: %s - found: %s for -> %s" % (expected, result, description)
		assert expected == result
	
	def assertTrue(self, condition, description):
		if not condition: print description + " => NOT OK"
		assert condition

	def load_music(self):
		music = Music("E:\\Music\\Bloc Party - Silent Alarm\\01 - Like Eating Glass.mp3")
		music.length = 261
		music.played_at = int(time.time()) - 40
		return music
	
class AudioScrobblerServiceFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		f = open("E:\\as.pwd", "rb")
		self.pwd = f.read().replace(" ", "")
		f.close()
		self.title = "Audio scrobbler service tests"

	def run(self):
		if self.pwd:
			as_service = self.sl.as_service
			as_service.set_credentials(AudioScrobblerUser("doug_fernando", self.pwd))
			as_service.login()
		
			self.assertTrue(as_service.logged, "Logging")
			
			music = self.load_music()
			result = as_service.now_playing(music)
			self.assertTrue(result, "Sent now playing to AS")
			
			result = as_service.send([music])
			self.assertTrue(result, "Sent music to AS")

class MusicsFactoryFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music factory tests"
	
	def run(self):
		mf = self.sl.music_factory
		
		musics = mf.load_all_musics("E:\\Music\\Bloc Party - Silent Alarm\\")
		self.assertEquals(16, len(musics), "Num of musics loaded")
		
		musics = mf.load_all_musics("E:\\Music\\Muse - Absolution")
		self.assertEquals(14, len(musics), "Num of musics loaded")

class FileSystemServicesFixture(Fixture):
	def __init__(self):
		self.title = "File System Services tests"

	def run(self):
		t = os.listdir("E:\\Music\\Bloc Party - Silent Alarm\\")
		
		fss = FileSystemServices()
		files = fss.find_all_files("E:\\Music\\Bloc Party - Silent Alarm\\", ".mp3")
		self.assertEquals(16, len(files), "Num of files loaded")
		
		files = fss.find_all_files("E:\\Music\\Muse - Absolution", ".mp3")
		self.assertEquals(14, len(files), "Num of files loaded")


class MusicHistoryRepositoryFixture(Fixture):		
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music history repository tests"

	def run(self):
		repos = self.sl.history_repository
		repos.clear_history()

		musics = repos.load_all_history()
		self.assertTrue(len(musics) == 0, "Repository empty")

		music = self.load_music()
		repos.save_music(music)
		musics = repos.load_all_history()
		self.assertTrue(len(musics) > 0, "Repository not empty")

class MusicFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music tests"

	def run(self):
		music = self.load_music()
		music.position = 135
		
		self.assertTrue(unicode(music.title) == u"Like Eating Glass", "Music title")
		self.assertTrue(unicode(music.artist) == u"Bloc Party", "Music artist")
		self.assertTrue(unicode(music.album) == u"Silent Alarm [Japan Bonus Trac", "Music Album")
		
		length_formatted = music.length_formatted()
		self.assertTrue(unicode("04:21") == unicode(length_formatted), "Correct length formatted") 
		
		current_pos_formatted = music.current_position_formatted()
		self.assertTrue(unicode("02:15") == unicode(current_pos_formatted), "Current position formatted")
		
		self.assertTrue(music.remove_X00("ABC\x00") == "ABC", "Remove unicode spaces")
		
		music.get_player_position_in_seconds = lambda: 200
		self.assertTrue(music.can_update_position(), "Can update position")
		self.assertTrue(music.can_update_position() == False, "Cannot update position")

		music.get_player_position_in_seconds = lambda: 20
		self.assertTrue(music.can_be_added_to_history() == False, "Cannot add to history")
		music.length = 600
		music.get_player_position_in_seconds = lambda: 200
		self.assertTrue(music.can_be_added_to_history() == False, "Cannot add to history")
		music.get_player_position_in_seconds = lambda: 250
		self.assertTrue(music.can_be_added_to_history(), "Can add to history")
		music.length = 261
		music.get_player_position_in_seconds = lambda: 135
		self.assertTrue(music.can_be_added_to_history(), "Can add to history")

		music.is_playing = lambda: True
		self.assertEquals("Playing", music.get_status_formatted(), "playing status formatted")

		music.is_playing = lambda: False
		self.assertEquals("Stopped", music.get_status_formatted(), "stopped status formatted")


class UserFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "User tests"

	def run(self):
		user = AudioScrobblerUser("doug_fernando", "hiaa29348")
		self.assertTrue(user.username == "doug_fernando", "Username")
		self.assertTrue(user.password == "894f117cc2e31a7195ad628cadf8da1a", "Password hashed")

		user2 = AudioScrobblerUser("doug_fernando", "abc", True)
		self.assertTrue(user2.username == "doug_fernando", "Username")
		self.assertTrue(user2.password == "abc", "Password")

class MusicPlayerFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music player tests"

	def run(self):
		audio_player = FakePlayer()
		
		player = MusicPlayer(None, audio_player)
		player.__class__.current_volume = -1
		
		player.configure_volume()
		
		self.assertTrue(player.__class__.current_volume == 2, "Currenct volume")
		self.assertTrue(player.volume_step == 1, "Correct step")
		
		player.loaded = True
		
		player.__class__.current_volume = 0
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 1, "Current volume")

		player.__class__.current_volume = 9
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 10, "Current volume")
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 10, "Current volume")
		
		player.__class__.current_volume = 2
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 1, "Current volume")
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 0, "Current volume")
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 0, "Current volume")

		player.__class__.current_volume = 2
		self.assertTrue(player.current_volume_percentage() == 20, "Current percentage")
		
		player.__class__.current_volume = 0
		self.assertTrue(player.current_volume_percentage() == 0, "Current percentage")
		
		player.__class__.current_volume = 10
		self.assertTrue(player.current_volume_percentage() == 100, "Current percentage")
		
		player.__class__.current_volume = 2

class FakePlayer(object):
	def max_volume(self):
		return 10;
	
	def set_volume(self, value):
		pass

class MusicHistoryFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music history tests"

	def run(self):
		self.music_history_tests()
		self.send_batches_tests()
	
	def music_history_tests(self):
		ms = []
		for i in range(10):
			ms.append(self.load_music())
		
		repos = MusicHistoryRepository(None)
		repos.load_all_history = lambda: ms
		repos.clear_history = lambda: None
		
		as_service = AudioScrobblerService(None)
		empty = []
		as_service.send = lambda musics:empty.append(1)
		
		m_h = MusicHistory(repos, as_service)
		m_h.send_to_audioscrobbler()
		
		self.assertTrue(len(empty) > 0, "Simple send expected")
		
		for i in range(50):
			ms.append(self.load_music())
		
		empty.pop()
		old_method = m_h.send_batches_to_audioscrobbler
		m_h.send_batches_to_audioscrobbler = lambda musics: None

		m_h.send_to_audioscrobbler()
		
		self.assertTrue(len(empty) == 0, "Batch expected")
		
	def send_batches_tests(self):
		musics = [i for i in range(135)]
		l = []
		m_h = MusicHistory(None, None)
		m_h.send_batch = lambda batch: l.append(len(batch))
		m_h.send_batches_to_audioscrobbler(musics)
		self.assertTrue(l[0] == 50, "Batch 1")
		self.assertTrue(l[1] == 50, "Batch 2")
		self.assertTrue(l[2] == 35, "Batch 3")
	
class AudioScrobblerUserRepositoryFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "AudioScrobblerUserRepository tests"
		f = open("E:\\as.pwd", "rb")
		self.pwd = f.read().replace(" ", "")
		f.close()

	def run(self):
		u = AudioScrobblerUser("doug_fernando", self.pwd)
		self.sl.user_repository.save(u)
		u2 = self.sl.user_repository.load()
		
		self.assertEquals(u.username, u2.username, "Users")
		self.assertEquals(u.password, u2.password, "Passwords")
	

class MusicListFixture(Fixture):
	def run(self):
		musics = [i for i in range(3)]
		mf = MusicsFactory(None)
		mf.load_all_musics = lambda m: musics
		
		ml = MusicList(mf, None, None)
		
		self.assertEquals("1 / 3", ml.current_position_formated(), "Correct first position")
		self.assertTrue(ml.move_previous() == False, "Cannot move back from start")
		self.assertTrue(ml.move_next(), "Can move forward")
		self.assertEquals("2 / 3", ml.current_position_formated(), "Correct sec position")
		self.assertTrue(ml.move_next(), "Can move forward")
		self.assertEquals("3 / 3", ml.current_position_formated(), "Correct last position")
		self.assertTrue(ml.move_next() == False, "Cannot move forward")
		self.assertEquals("3 / 3", ml.current_position_formated(), "Correct last position")
		self.assertTrue(ml.move_previous(), "Can move back")
		self.assertEquals("2 / 3", ml.current_position_formated(), "Correct sec position")
		self.assertTrue(ml.move_previous(), "Can move back")
		self.assertTrue(ml.move_previous() == False, "Cannot move back")
		

class PlayerUIPresenterFixture(Fixture):
	def run(self):
		pass

class Fixtures(object):
	def __init__(self):
		self.tests = [
			MusicsFactoryFixture(),
			MusicFixture(),
			MusicPlayerFixture(),
			MusicListFixture(),
			MusicHistoryFixture(),
			UserFixture(),
			AudioScrobblerUserRepositoryFixture(),
			MusicHistoryRepositoryFixture(),
			#AudioScrobblerServiceFixture(),
			FileSystemServicesFixture(),
			#DbHelper
			#PlayerUI 
			PlayerUIPresenterFixture()
			#DirectoryNavigatorContent
			#DirectorySelector
		]
		
	
	def run(self):
		for test in self.tests:
			test.run()
		
		appuifw.note(unicode("All %i test suites passed!" % len(self.tests)), "info")

##########################################################
######################### MAIN 


if __name__ == u"__main__":
	
	sl = ServiceLocator()
	ui = PlayerUI(sl)

	try:
		ui.start()
	finally:
		ui.close()
		sl.close()
		print "bye" 




		