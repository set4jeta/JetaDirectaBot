# esports_extension/utils/buttons.py

from nextcord.ui import View, Button, button
from nextcord import Interaction, ButtonStyle

class ScoreButtonView(View):
    def __init__(self, blue_wins: int, red_wins: int ): #timeout: float = 10
        super().__init__(timeout=None)
        self.blue_wins = blue_wins
        self.red_wins = red_wins

    @button(label="Ver marcador", style=ButtonStyle.gray)
    async def reveal_score(self, button: Button, interaction: Interaction):
        await interaction.response.send_message(
            f"📊 Marcador actual: **{self.blue_wins} - {self.red_wins}**",
            ephemeral=True
        )