import logging
import os
from pathlib import Path

from discord.ext import commands
from tabulate import tabulate
from dotenv import load_dotenv

from utils.bot import bot, s
from utils.logger import get_logger

# Load environment variables and logger setup
load_dotenv()
logger = get_logger("Sync")


# Constants
COG_DIRECTORIES = ["./commands", "./Features"]


@bot.command(name="load_cogs", help="Loads all cogs in the COG_DIRECTORIES list.")
@commands.is_owner()
async def load_cogs_command(ctx):
	"""
	Loads all cogs specified in the `COG_DIRECTORIES` list and sends a message pre- and post-execution.

	The command is restricted to the bot owner only. It facilitates the bot owner to dynamically
	load all defined cogs in the bot at runtime.

	:param ctx: The context in which the command was invoked
	:type ctx: commands.Context
	:return: None
	:rtype: None
	"""
	await ctx.send("Loading cogs...")
	await load_cogs()
	await ctx.send("Cogs loaded successfully.")


# Helper Functions
def log_command_details(guild_name, commands):
	"""
	Logs the details of provided commands for a specified guild. Each command's
	name, description, and type is gathered and formatted into a tabular
	representation for logging purposes. If no description exists for a command,
	a placeholder text is used.

	:param guild_name: The name of the guild for which the commands are being logged
	:param commands: A list of command objects where each command includes name,
		description, and type attributes
	:return: None
	"""
	command_data = [
		[cmd.name, cmd.description or "No description provided.", cmd.type.name]
		for cmd in commands
	]

	command_table = tabulate(
		command_data,
		headers=["Command Name", "Description", "Type"],
		tablefmt="fancy_grid"
	)
	logger.info(f"Commands for {guild_name}:\n{command_table}")


async def attach_databases():
	"""
	Attaches specific collections as bot attributes and logs the status.
	Groups successfully attached (`✅`) and failed (`❌`) attributes.
	"""
	success_logs = [f"{s}🔄 Starting database attachment process...\n"]
	failed_logs = []

	try:
		# Initialize DatabaseManager first (all other managers depend on it)
		from storage.database_manager import db_manager
		try:
			await db_manager.initialize()
			result, is_success = await attach_attribute("db_manager", db_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as db_error:
			failed_logs.append(f"{s}❌ db_manager → Error: {db_error}\n")
			raise  # Can't continue without db_manager

		# Initialize Cache Manager (uses db_manager's collections)
		from storage.cache import create_cache_manager
		try:
			cache_manager = create_cache_manager(db_manager)
			result, is_success = await attach_attribute("cache_manager", cache_manager)
			(success_logs if is_success else failed_logs).append(result)

			# Update global cache manager reference
			import storage.cache as cache_module
			cache_module.cache_manager = cache_manager

		except Exception as cache_error:
			failed_logs.append(f"{s}❌ cache_manager → Error: {cache_error}\n")

		# Initialize unified GuildConfigManager (handles both structured config and flat settings)
		try:
			from storage.config_manager import get_guild_config_manager
			guild_config_manager = await get_guild_config_manager(db_manager)
			result, is_success = await attach_attribute("guild_config_manager", guild_config_manager)
			(success_logs if is_success else failed_logs).append(result)

			# Register as the global config manager (replaces old ConfigManager)
			result, is_success = await attach_attribute("storage_config_manager", guild_config_manager)
			(success_logs if is_success else failed_logs).append(result)
		except Exception as config_error:
			failed_logs.append(f"{s}❌ guild_config_manager / storage_config_manager → Error: {config_error}\n")
	except Exception as e:
		failed_logs.append(f"{s}❌ Encountered a critical error during database attachment → {e}\n")

	# Add group headers for success and failure logs
	if failed_logs:
		failed_logs.insert(0, f"{s}❌ Failed to attach the following attributes:\n")
	if success_logs:
		success_logs.insert(1 if failed_logs else 0, f"{s}✅ Successfully attached the following attributes:\n")

	# Combine and log the final result
	final_log = failed_logs + success_logs
	logger.info("\n" + "".join(final_log) + f"{s}✅ Database attachment process completed.\n")


async def attach_attribute(attribute_name, attribute_value):
	"""
	Safely attaches an attribute to the bot and returns its status.
	"""
	try:
		setattr(bot, attribute_name, attribute_value)  # Attach to bot
		return f"{s}✅ {attribute_name}: {attribute_value}\n", True
	except Exception as e:
		return f"{s}❌ {attribute_name} → Error: {e}\n", False


async def load_cogs():
	"""
	Load all cogs from specified directories in `COG_DIRECTORIES`.
	Group and log successful loads (`✅`) and failed ones (`❌`) together.
	"""
	success_logs = [f"{s}🔄 Starting cog loading process...\n"]
	failed_logs = []

	for base_dir in COG_DIRECTORIES:
		for root, _, files in os.walk(base_dir):
			for file in files:
				if not file.endswith(".py") or file.startswith("__"):
					continue

				module_name = generate_cog_module_name(root, file)

				# Skip specific cases
				if module_name in bot.extensions:
					success_logs.append(f"{s}🔄 Skipping already loaded cog: {module_name}\n")
					continue

				# Safely load the cog and append to appropriate log
				result, is_success = await safely_load_cog(module_name, os.path.join(root, file))
				if result is None:
					continue
				if is_success:
					success_logs.append(result)
				else:
					failed_logs.append(result)

	# Add summary headers and combine logs
	if failed_logs:
		failed_logs.insert(0, f"{s}❌ Failed to load the following cogs:\n")
	success_logs.append(f"{s}✅ Successfully loaded the following cogs:\n")

	# Combine and log the final output
	final_logs = failed_logs + success_logs if failed_logs else success_logs
	logger.info("\n" + "".join(final_logs) + f"{s}✅ Cog loading process completed.\n")


async def safely_load_cog(module, file_path):
	"""
	Dynamically import and load a cog module.
	Returns the result as a formatted string and a success status.
	Skips files that don't define a setup() function.
	"""
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			content = f.read()
		if "\ndef setup(" not in content and "\nasync def setup(" not in content:
			logger.debug(f"Skipping {module} — no setup() function")
			return None, None
	except Exception:
		pass

	try:
		await bot.load_extension(module)
		return f"{s}✅ {module}\n", True
	except Exception as e:
		return f"{s}❌ {module} → Error: {e}\n", False


def generate_cog_module_name(root, file):
	"""
	Helper to generate the fully qualified module name from root and file.
	"""
	# Normalize paths and remove leading "./" if present
	relative_path = os.path.relpath(os.path.join(root, file), start=str(Path("."))).replace("\\", "/")
	# Convert to Python module format
	module_name = relative_path.replace("/", ".").removesuffix(".py")
	logger.info(f"Generating module name for {file}: {module_name}")
	return module_name


def log_prefix_commands(commands):
	"""
	Logs all prefix commands with their details in a tabular format.
	"""
	command_data = [[cmd.name, cmd.help or "No description", ", ".join(cmd.aliases) or "None"] for cmd in commands]
	command_table = tabulate(command_data, headers=["Command", "Description", "Aliases"], tablefmt="fancy_grid")
	logger.info(f"Prefix Commands:\n{command_table}")


async def cache_guild_roles():
	"""Cache guild roles for all guilds the bot is in."""
	from utils.bot import bot

	if hasattr(bot, 'cache_manager'):
		cached_count = 0
		for guild in bot.guilds:
			try:
				await bot.cache_manager.cache_roles(guild)
				cached_count += 1
				logger.debug(f"Cached roles for guild: {guild.name} ({guild.id})")
			except Exception as e:
				logger.error(f"Failed to cache roles for guild {guild.name} ({guild.id}): {e}")
		logger.info(f"Roles cached successfully for {cached_count} guild(s).")
	else:
		logger.error("Cache manager not available")