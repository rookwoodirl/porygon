import discord

class NewGame:
    def champion_emote(self):
        try:
            # Get the guild from the message
            if not hasattr(self, '_guild'):
                # If we don't have the guild cached, try to get it from the bot
                bot = discord.Client.get_client()
                if bot is None:
                    return f':{self.champion}:'
                # Get the first guild the bot is in
                guild = next(iter(bot.guilds), None)
                if guild is None:
                    return f':{self.champion}:'
                self._guild = guild
            
            # Try to find the emote in the guild
            emote = discord.utils.get(self._guild.emojis, name=self.champion)
            return str(emote) if emote else f':{self.champion}:'
        except Exception as e:
            print(f"Error getting emote for {self.champion}: {e}")
            return f':{self.champion}:' 