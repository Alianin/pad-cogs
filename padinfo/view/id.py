from typing import TYPE_CHECKING, List, Optional

from discordmenu.embed.base import Box
from discordmenu.embed.components import EmbedThumbnail, EmbedMain, EmbedField
from discordmenu.embed.text import Text, BoldText, LabeledText, HighlightableLinks, LinkedText
from discordmenu.embed.view import EmbedView

from tsutils.enums import Server, CardPlusModifier
from tsutils.menu.footers import embed_footer_with_state
from tsutils.query_settings import QuerySettings

from padinfo.common.config import UserConfig
from padinfo.common.emoji_map import get_awakening_emoji, get_emoji
from padinfo.common.external_links import puzzledragonx
from padinfo.view.base import BaseIdView
from padinfo.view.common import get_monster_from_ims, invalid_monster_text, leader_skill_header
from padinfo.view.components.monster.header import MonsterHeader
from padinfo.view.components.monster.image import MonsterImage
from padinfo.view.components.view_state_base_id import ViewStateBaseId, MonsterEvolution

if TYPE_CHECKING:
    from dbcog.models.monster_model import MonsterModel
    from dbcog.models.awakening_model import AwakeningModel


def alt_fmt(monsterevo, state):
    if monsterevo.monster.is_equip:
        fmt = "⌈{}⌉"
    elif not monsterevo.evolution or monsterevo.evolution.reversible:
        fmt = "{}"
    else:
        fmt = "⌊{}⌋"
    return fmt.format(monsterevo.monster.monster_no_na)


class IdViewState(ViewStateBaseId):
    nadiff_na_only_text = ', which is only in NA'
    nadiff_jp_only_text = ', which is only in JP'
    nadiff_identical_text = ', which is the same in NA & JP'

    def __init__(self, original_author_id, menu_type, raw_query, query, color, monster: "MonsterModel",
                 alt_monsters: List[MonsterEvolution], is_jp_buffed: bool, query_settings: QuerySettings,
                 transform_base, true_evo_type_raw, acquire_raw, base_rarity,
                 fallback_message: str = None, use_evo_scroll: bool = True, reaction_list: List[str] = None,
                 is_child: bool = False, extra_state=None):
        super().__init__(original_author_id, menu_type, raw_query, query, color, monster,
                         alt_monsters, is_jp_buffed, query_settings,
                         use_evo_scroll=use_evo_scroll,
                         reaction_list=reaction_list,
                         extra_state=extra_state)
        self.fallback_message = fallback_message
        self.is_child = is_child
        self.acquire_raw = acquire_raw
        self.base_rarity = base_rarity
        self.transform_base: "MonsterModel" = transform_base
        self.true_evo_type_raw = true_evo_type_raw

    def serialize(self):
        ret = super().serialize()
        ret.update({
            'pane_type': IdView.VIEW_TYPE,
            'is_child': self.is_child,
            'message': self.fallback_message,
        })
        return ret

    @classmethod
    async def deserialize(cls, dbcog, user_config: UserConfig, ims: dict):
        # for numberscroll getting to a gap in monster book, or 1, or last monster
        if ims.get('unsupported_transition'):
            return None
        monster = await get_monster_from_ims(dbcog, ims)
        alt_monsters = cls.get_alt_monsters_and_evos(dbcog, monster)
        transform_base, true_evo_type_raw, acquire_raw, base_rarity = \
            await IdViewState.do_query(dbcog, monster)

        raw_query = ims['raw_query']
        # This is to support the 2 vs 1 monster query difference between ^ls and ^id
        query = ims.get('query') or raw_query
        query_settings = QuerySettings.deserialize(ims.get('query_settings'))
        menu_type = ims['menu_type']
        original_author_id = ims['original_author_id']
        use_evo_scroll = ims.get('use_evo_scroll') != 'False'
        reaction_list = ims.get('reaction_list')
        fallback_message = ims.get('message')
        is_child = ims.get('is_child')
        is_jp_buffed = dbcog.database.graph.monster_is_discrepant(monster)

        return cls(original_author_id, menu_type, raw_query, query, user_config.color, monster,
                   alt_monsters, is_jp_buffed, query_settings,
                   transform_base, true_evo_type_raw, acquire_raw, base_rarity,
                   fallback_message=fallback_message,
                   use_evo_scroll=use_evo_scroll,
                   reaction_list=reaction_list,
                   is_child=is_child,
                   extra_state=ims)

    async def set_server(self, dbcog, server: Server):
        self.query_settings.server = server
        self.monster = dbcog.database.graph.get_monster(self.monster.monster_id, server=server)
        self.alt_monsters = self.get_alt_monsters_and_evos(dbcog, self.monster)
        transform_base, true_evo_type_raw, acquire_raw, base_rarity = await self.do_query(dbcog, self.monster)
        self.transform_base = transform_base
        self.true_evo_type_raw = true_evo_type_raw
        self.acquire_raw = acquire_raw
        self.base_rarity = base_rarity

    @classmethod
    async def do_query(cls, dbcog, monster):
        db_context = dbcog.database
        acquire_raw, base_rarity, transform_base, true_evo_type_raw = \
            await IdViewState._get_monster_misc_info(db_context, monster)

        return transform_base, true_evo_type_raw, acquire_raw, base_rarity

    @classmethod
    async def _get_monster_misc_info(cls, db_context, monster):
        transform_base = db_context.graph.get_transform_base(monster)
        true_evo_type_raw = db_context.graph.true_evo_type(monster).value
        acquire_raw = db_context.graph.monster_acquisition(monster)
        base_rarity = db_context.graph.get_base_monster(monster).rarity
        return acquire_raw, base_rarity, transform_base, true_evo_type_raw

    def set_na_diff_invalid_message(self, ims: dict) -> bool:
        message = self.get_na_diff_invalid_message()
        if message is not None:
            ims['message'] = message
            return True
        return False

    def get_na_diff_invalid_message(self) -> Optional[str]:
        monster: "MonsterModel" = self.monster
        if monster.on_na and not monster.on_jp:
            return invalid_monster_text(self.query, monster, self.nadiff_na_only_text, link=True)
        if monster.on_jp and not monster.on_na:
            return invalid_monster_text(self.query, monster, self.nadiff_jp_only_text, link=True)
        if not self.is_jp_buffed:
            return invalid_monster_text(self.query, monster, self.nadiff_identical_text, link=True)
        return None


def _get_awakening_text(awakening: "AwakeningModel"):
    return get_awakening_emoji(awakening.awoken_skill_id, awakening.name)


def _killer_latent_emoji(latent_name: str):
    return get_emoji('latent_killer_{}'.format(latent_name.lower()))


def _get_awakening_emoji_for_stats(m: "MonsterModel", i: int):
    return get_awakening_emoji(i) if m.awakening_count(i) and not m.is_equip else ''


def _get_stat_text(stat, lb_stat, icon):
    return Box(
        Text(str(stat)),
        Text("({})".format(lb_stat)) if lb_stat else None,
        Text(icon) if icon else None,
        delimiter=' '
    )


def _monster_is_enhance(m: "MonsterModel"):
    return any(x if x.name == 'Enhance' else None for x in m.types)


def evos_embed_field(state: ViewStateBaseId):
    field_text = "**Evos**"
    help_text = ""
    # this isn't used right now, but maybe later if discord changes the api for embed titles...?
    help_link = "https://github.com/TsubakiBotPad/pad-cogs/wiki/Evolutions-mini-view"
    legend_parts = []
    if any(not alt_evo.evolution.reversible for alt_evo in state.alt_monsters if alt_evo.evolution):
        legend_parts.append("⌊Irreversible⌋")
    if any(alt_evo.monster.is_equip for alt_evo in state.alt_monsters):
        legend_parts.append("⌈Equip⌉")
    if legend_parts:
        help_text = ' – Help: {}'.format(" ".join(legend_parts))
    return EmbedField(
        field_text + help_text,
        HighlightableLinks(
            links=[LinkedText(alt_fmt(me, state), puzzledragonx(me.monster)) for me in state.alt_monsters],
            highlighted=next(i for i, me in enumerate(state.alt_monsters)
                             if state.monster.monster_id == me.monster.monster_id)
        )
    )


class IdView(BaseIdView):
    VIEW_TYPE = 'Id'

    @staticmethod
    def normal_awakenings_row(m: "MonsterModel"):
        normal_awakenings = len(m.awakenings) - m.superawakening_count
        normal_awakenings_emojis = [_get_awakening_text(a) for a in m.awakenings[:normal_awakenings]]
        return Box(*[Text(e) for e in normal_awakenings_emojis], delimiter=' ')

    @staticmethod
    def super_awakenings_row(m: "MonsterModel"):
        normal_awakenings = len(m.awakenings) - m.superawakening_count
        super_awakenings_emojis = [_get_awakening_text(a) for a in m.awakenings[normal_awakenings:]]
        return Box(
            Text(get_emoji('sa_questionmark')),
            *[Text(e) for e in super_awakenings_emojis],
            delimiter=' ') if len(super_awakenings_emojis) > 0 else None

    @staticmethod
    def all_awakenings_row(m: "MonsterModel", transform_base):
        if len(m.awakenings) == 0:
            return Box(Text('No Awakenings'))

        return Box(
            Box(
                '\N{UP-POINTING RED TRIANGLE}' if m != transform_base else '',
                IdView.normal_awakenings_row(m),
                delimiter=' '
            ),
            Box(
                '\N{DOWN-POINTING RED TRIANGLE}',
                IdView.all_awakenings_row(transform_base, transform_base),
                delimiter=' '
            ) if m != transform_base else None,
            IdView.super_awakenings_row(m),
        )

    @staticmethod
    def killers_row(m: "MonsterModel", transform_base):
        killers = m.killers if m == transform_base else transform_base.killers
        killers_text = 'Any' if 'Any' in killers else \
            ' '.join(_killer_latent_emoji(k) for k in killers)
        return Box(
            BoldText('Available killers:'),
            Text('\N{DOWN-POINTING RED TRIANGLE}' if m != transform_base else ''),
            Text('[{} slots]'.format(m.latent_slots if m == transform_base
                                     else transform_base.latent_slots)),
            Text(killers_text),
            delimiter=' '
        )

    @staticmethod
    def misc_info(m: "MonsterModel", true_evo_type_raw: str, acquire_raw: str, base_rarity: str):
        rarity = Box(
            LabeledText('Rarity', str(m.rarity)),
            Text('({})'.format(LabeledText('Base', str(base_rarity)).to_markdown())),
            Text("" if m.orb_skin_id is None else "(Orb Skin)"),
            delimiter=' '
        )

        cost = LabeledText('Cost', str(m.cost))
        acquire = BoldText(acquire_raw) if acquire_raw else None
        series = BoldText(m.series.name_en) if m.series else None
        valid_true_evo_types = ("Reincarnated", "Assist", "Pixel", "Super Reincarnated")
        true_evo_type = BoldText(true_evo_type_raw) if true_evo_type_raw in valid_true_evo_types else None

        return Box(rarity, cost, series, acquire, true_evo_type)

    @staticmethod
    def stats(m: "MonsterModel", cardplus: CardPlusModifier):
        plus = 297 if cardplus == CardPlusModifier.plus297 else 0
        hp, atk, rcv, weighted = m.stats(plus=plus)
        lb_hp, lb_atk, lb_rcv, lb_weighted = m.stats(plus=297, lv=110) if m.limit_mult > 0 else (None, None, None, None)
        return Box(
            LabeledText('HP', _get_stat_text(hp, lb_hp, _get_awakening_emoji_for_stats(m, 1))),
            LabeledText('ATK', _get_stat_text(atk, lb_atk, _get_awakening_emoji_for_stats(m, 2))),
            LabeledText('RCV', _get_stat_text(rcv, lb_rcv, _get_awakening_emoji_for_stats(m, 3))),
            LabeledText('Fodder EXP', "{:,}".format(m.fodder_exp)) if _monster_is_enhance(m) else None
        )

    @staticmethod
    def stats_header(m: "MonsterModel", cardplus: CardPlusModifier):
        voice_emoji = get_awakening_emoji(63) if m.awakening_count(63) and not m.is_equip else ''
        # TODO: Get a +0 emoji for the +0 setting
        plus_297_emoji = get_emoji('plus_297') if cardplus == CardPlusModifier.plus297 else get_emoji('plus_0')
        header = Box(
            Text(voice_emoji),
            Text(plus_297_emoji),
            Text('Stats'),
            Text('(LB, +{}%)'.format(m.limit_mult)) if m.limit_mult else None,
            delimiter=' '
        )
        return header

    @staticmethod
    def active_skill_header(m: "MonsterModel", transform_base):
        active_skill = m.active_skill
        if m == transform_base:
            active_cd = "({} -> {})".format(active_skill.turn_max, active_skill.turn_min) \
                if active_skill else 'None'
        else:
            base_skill = transform_base.active_skill
            base_cd = ' (\N{DOWN-POINTING RED TRIANGLE} {} -> {})'.format(base_skill.turn_max,
                                                                          base_skill.turn_min) \
                if base_skill else 'None'

            active_cd = '({} cd)'.format(active_skill.turn_min) if active_skill else 'None'
            active_cd += base_cd
        return Box(
            BoldText('Active Skill'),
            BoldText(active_cd),
            delimiter=' '
        )

    @classmethod
    def embed(cls, state: IdViewState):
        m = state.monster
        fields = [
            EmbedField(
                '/'.join(['{}'.format(t.name) for t in m.types]),
                Box(
                    IdView.all_awakenings_row(m, state.transform_base),
                    IdView.killers_row(m, state.transform_base)
                )
            ),
            EmbedField(
                'Inheritable' if m.is_inheritable else 'Not inheritable',
                IdView.misc_info(m, state.true_evo_type_raw, state.acquire_raw, state.base_rarity),
                inline=True
            ),
            EmbedField(
                IdView.stats_header(m, state.query_settings.cardplus).to_markdown(),
                IdView.stats(m, state.query_settings.cardplus),
                inline=True
            ),
            EmbedField(
                IdView.active_skill_header(m, state.transform_base).to_markdown(),
                Text(m.active_skill.desc if m.active_skill else 'None')
            ),
            EmbedField(
                leader_skill_header(m, state.query_settings.lsmultiplier, state.transform_base).to_markdown(),
                Text(m.leader_skill.desc if m.leader_skill else 'None')
            ),
            evos_embed_field(state)
        ]

        return EmbedView(
            EmbedMain(
                color=state.color,
                title=MonsterHeader.fmt_id_header(m,
                                                  state.alt_monsters[0].monster.monster_id == cls.TSUBAKI,
                                                  state.is_jp_buffed).to_markdown(),
                url=puzzledragonx(m)),
            embed_thumbnail=EmbedThumbnail(MonsterImage.icon(m)),
            embed_footer=embed_footer_with_state(state),
            embed_fields=fields)
