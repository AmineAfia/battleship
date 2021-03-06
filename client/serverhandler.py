import logging, socket, sys
from threading import Thread

from messageparser import *
from playingfield import Orientation

reportCodes = {
	11: "Begin_Turn",
	13: "Update_Own_Field",
	14: "Update_Enemy_Field",
	15: "Chat_Broadcast",
	16: "Update_Lobby",
	17: "Game_Ended",
	18: "Begin_Ship_Placing",
	19: "Game_Aborted",
	21: "Successful_Move",
	22: "Successful_Attack",
	23: "Surrender_Accepted",
	24: "Successful_Special_Attack",
	27: "Successful_Game_Join",
	28: "Successful_Game_Create",
	29: "Successful_Ship_Placement",
	31: "Illegal_Move",
	32: "Illegal_Special_Attack",
	37: "Illegal_Game_Definition",
	38: "Illegal_Ship_Placement",
	39: "Illegal_Attack",
	40: "Message_Not_Recognized",
	41: "Not_Your_Turn",
	43: "Not_In_Any_Game",
	47: "Game_Join_Denied",
	48: "Game_Preparation_Ended"
}

orientationCodes = {
	Orientation.NORTH: "N",
	Orientation.WEST:  "W",
	Orientation.SOUTH: "S",
	Orientation.EAST:  "E"
}

class ServerHandler:
	"""
	Communicates with the server.

	Author:
		Maximilian Hess <mail@maximilianhess.com>
	"""

	def setNickname(self, nickname):
		"""
		Resets the nickname.

		Args:
			nickname: the new nickname
		"""

		self.__sendMessage("nickname_set", {"name": nickname})

	"""
	Sent whenever the server noticed a change in the lobby.

		number_of_clients:[number n];
			The total number of clients currently connected to the server.

		number_of_games:[number m];
			The total number of open games on this server.

		game_name_0:[name];...;game_name_m-1:[name];
			The name of this game.

		game_players_count_0:[1|2];...;game_players_m-1:[1|2];
			The number of players currently in this game (1 or 2).

		game_player_0_i:[identifier];...;game_player_m-1_i:[identifier]
			For each game k from(0..m-1) games this maps game_players_count_k players to the game by use of their
			identifier. The first value in the name of the parameter is the related game.

		player_name_0:[name];...;player_name_n-1:[name];
			MAY be an empty string, if no nickname was set prior to this report.

		player_identifier_0:[identifier];...;player_identifier_n-1:[identifier];
			Per-server-unique identifier (implementations may map any string as identifier)
	"""
	def __onUpdateLobby(self, params):
		from backend import GameInformation, PlayerInformation

		games   = []
		players = []

		# extract players count and games count
		playersTotal = int(params["number_of_clients"])
		gamesTotal   = int(params["number_of_games"])

		"""
		We have to make sure that all players in the game actually exist. Therefore players are extracted before the
		games.
		"""

		# extract players
		playersCounter = 0
		for param, value in params.items():
			if param.startswith("player_identifier_"):

				# make sure that there are not more players than passed by players counter
				if playersCounter >= playersTotal:
					continue
				playersCounter += 1

				# extract counter and nickname if there is one...
				if "player_name_" + param[18:] in params:
					nickname = params["player_name_" + param[18:]]

				players.append(PlayerInformation(value, nickname))

		# extract games
		gamesCounter = 0
		for param, value in params.items():
			if param.startswith("game_name_"):

				# make sure that there are not more games than passed by games counter
				if gamesCounter >= gamesTotal:
					continue
				gamesCounter += 1

				counter = int(param[10:])
				numberOfPlayers = int(params["game_players_count_" + str(counter)])
				if numberOfPlayers > 2:
					logging.error("Update_Lobby error: To many players.")

				# find the players of this game
				# validate that the players exist
				player0 = params["game_player_" + str(counter) + "_0"]
				game = GameInformation(value, player0)
				if numberOfPlayers > 1:
					player1 = params["game_player_" + str(counter) + "_1"]
					game.players.append(player1)

				games.append(game)

		self.__backend.onLobbyUpdates(players, games)

	def joinGame(self, gameId):
		"""
		Sends a joinGame request to the server.

		Args:
			gameId: the identifier of the game
		"""

		self.__sendMessage("game_join", {"name": gameId})

	def createGame(self, gameId):
		"""
		Sends a new createGame request to the server.

		Args:
			gameId: the identifier of the new game
		"""

		self.__sendMessage("game_create", {"name": gameId})

	def leaveGame(self):
		"""
		Sends a leaveGame request to the server.
		"""

		self.__sendMessage("game_abort", {})

	def boardInit(self, ships):
		"""
		Sends the playing field to the server.

		Args:
			ships: a list of all ships
		"""

		params = {}

		i = 0
		for ship in ships:
			params["ship_" + str(i) + "_x"] = str(ship.rear.x)
			params["ship_" + str(i) + "_y"] = str(ship.rear.y)
			params["ship_" + str(i) + "_direction"] = orientationCodes[ship.orientation]
			i += 1

		self.__sendMessage("board_init", params)

	def attack(self, target):
		"""
		Sends an attack message.

		Args:
			target: the address of the field that is to be attacked
		"""

		self.__sendMessage("attack", {"coordinate_x": target.x, "coordinate_y": target.y})

	def specialAttack(self, target):
		"""
		Special-attacks the given field.

		Args:
			target: the address of the bottom-left field
		"""

		self.__sendMessage("special_attack", {"coordinate_x": target.x, "coordinate_y": target.y})

	def move(self, shipId, direction):
		"""
		Moves a ship on the own playing field.

		Args:
			shipId: the id of the ship
			direction: the direction
		"""

		self.__sendMessage("move", {"ship_id": shipId, "direction": orientationCodes[direction]})

	def sendChatMessage(self, msg):
		"""
		Sends a chat message.

		Args:
		    msg: the message
		"""

		self.__sendMessage("chat_send", {"text": msg})

	def capitulate(self):
		"""
		The player capitulates.
		"""

		self.__sendMessage("surrender", {})

	def __receiveLoop(self):
		while not self.__stopReceiveLoop:

			try:

				# read the first to byte to receive the byte size of the message
				size = self.__sock.recv(2)
				if not size:
					continue
				else:
					try:
						msg = self.__sock.recv(size[0] * 256 + size[1]).decode()
					except:
						logging.error("Failed to decode report: %s" % msg)
						continue
					messageType, params = self.__messageParser.decode(msg)
					#logging.debug("Receive: {}".format(msg))

					# validate that the status code exists
					status = int(params["status"])
					if status in reportCodes:
						logging.debug("%s received: %s" % (messageType, reportCodes[status]))

						if status is 15:
							self.__backend.onIncomingChatMessage(params["author_id"], params["timestamp"], params["message_content"])

						elif status is 16:														# Update_Lobby
							self.__onUpdateLobby(params)

						elif status is 17:														# Game_Ended
							self.__backend.onGameEnded(params)

						# game creation stuff
						elif status is 19:														# Game_Aborted
							self.__backend.onGameAborted()
						elif status is 23:
							self.__backend.onCapitulate()										# Surrender_Accepted
						elif status is 27 or status is 47:										# Successful_Game_Join
							self.__backend.onJoinGame(status is 27)								# or Game_Join_Denied
						elif status is 28:														# Successful_Game_Create
							self.__backend.onCreateGame(True)
						elif status is 29 or status is 38:										# Successful_Ship_Placement
							self.__backend.onPlaceShips(status is 29)							# or Illegal_Ship_Placement
						elif status is 37:														# Illegal_Game_Definition
							self.__backend.onIllegalGameDefinition()
						elif status is 48:														# Game_Preparation_Ended
							self.__backend.gamePreparationsEndedResponse()

						# game play stuff
						#  _ Begin_Turn
						#  - Successful_Move
						#  - Successful_Attack
						#  - Surrender_Accepted
						#  - Successful_Special_Attack
						#  - Illegal_Move
						#  - Illegal_Special_Attack
						#  - Illegal_Field
						#  - Illegal_Ship_Index
						#  - Illegal_Attack
						#  - Not_Your_Turn
						elif status is 11 or status is 21 or status is 22 or status is 23 or status is 24 or status is 31 \
								or status is 32 or status is 33 or status is 34 or status is 39 or status is 41:
							self.__backend.onGamePlayUpdate(status)

						# Begin_Ship_Placing
						elif status is 18:
							self.__backend.onBeginShipPlacing()

						# field updates
						elif status is 13:
							self.__backend.onUpdateOwnFields(params)
						elif status is 14:
							self.__backend.onUpdateEnemyFields(params)

						# bad error stuff
						#  - Message_Not_Recognized
						#  - Not_In_Any_Game (what? wtf? :D)
						elif status is 40 or status is 43:
							self.__backend.errorResponse(status)

					else:
						logging.debug("%s received with unknown status code." % (messageType))
			except Exception as ex:
				import traceback
				traceback.print_exc(file=sys.stdout)
				logging.error("Connection error: %s" % ex)
				logging.error("Lost connection to server! Cleaning up...")
				#self.__backend.onLostConnection()

	def __sendMessage(self, type, params):
		if not self.__connected:
			logging.error("Not connected.")
			return

		msg = self.__messageParser.encode(type, params)
		logging.debug("Sending message: %s"  % (msg))

		try:
			self.__sock.send(msg)
		except Exception as ex:
			logging.error("Failed to send message: %s" % ex)
			logging.error("Lost connection to server! Cleaning up...")
			#self.__backend.onLostConnection()

	def close(self):
		"""
		Closes the connection to the server.
		"""

		self.__stopReceiveLoop = True

	def isConnected(self):
		"""
		Returns True if the client is connected to a server or False if not.

		Returns: True if the client is connected to a server or False if not.
		"""

		return self.__connected

	def disconnect(self):
		"""
		Disconnects from the server the client is currently connected to.
		"""

		self.__stopReceiveLoop = True
		self.leaveGame()
		try:
			self.__sock.close()
			logging.info("Disconnected")
		except:
			logging.error("Disconnecting failed!")
		self.__connected = False

	def connect(self, hostname, port):
		"""
		Connects to a server.

		Args:
			hostname: the hostname or IP address of the server
			port: the port of the server
		"""

		try:
			self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.__sock.connect((hostname, port))
			self.__connected = True

			self.__stopReceiveLoop = False
			Thread(target=self.__receiveLoop).start()
			logging.info("Connected to '%s:%s'" % (hostname, port))

			return True

		except:
			logging.error("Failed to connect to server.")
			return False

	def __init__(self, backend):
		self.__backend = backend
		self.__messageParser = MessageParser()

		self.__connected = False
