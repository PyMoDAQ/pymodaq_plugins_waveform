"""Manager of the named sets of waveforms (one waveform per channel) of the Waveform designer

It is a :class:`~pymodaq_gui.managers.manager_base.ManagerBase` whose window is never shown: its actions (list of the
entries, new, copy, delete, save, reload, execute) are placed in the toolbar of the extension, that holds the settings.
An entry is a toml file of the ``waveforms`` folder of the PyMoDAQ configuration folder.
"""
from pathlib import Path
from typing import TYPE_CHECKING

import toml

from qtpy import QtWidgets

from pymodaq_gui.managers.manager_base import ManagerBase, ManagerActions
from pymodaq_gui.utils.widgets.combo import ComboBox
from pymodaq_utils.config import get_set_config_dir
from pymodaq_utils.logger import set_logger, get_module_name

if TYPE_CHECKING:
    from pymodaq_plugins_waveform.extensions.waveform_designer import WaveformDesigner

logger = set_logger(get_module_name(__file__))

FORMAT_VERSION = 1  # of the toml files: ``version``, then one ``[[channels]]`` table per channel


class WaveformManager(ManagerBase):
    """Save, name, and load the waveforms of the channels of a Waveform designer"""
    entry_type = 'waveform'
    entry_extension = '.toml'
    icon_name = 'graphic_eq'

    def init_extra(self, designer: 'WaveformDesigner' = None, **kwargs):
        super().init_extra(**kwargs)
        self.designer = designer

    def finish_init(self):
        self.enable_actions(True)

    def add_to_toolbar(self, toolbar: QtWidgets.QToolBar):
        """Put the combo of the entries and the actions in the toolbar of the extension (the window stays hidden)"""
        self.add_widget(ManagerActions.LIST_EXTERNAL, ComboBox(), toolbar=toolbar, tip='The saved waveforms')
        self.sync_entries_with(self.get_action(ManagerActions.LIST_EXTERNAL).widget)
        for action in (ManagerActions.EXECUTE, ManagerActions.NEW, ManagerActions.COPY, ManagerActions.SAVE,
                       ManagerActions.RELOAD, ManagerActions.DELETE):
            self.affect_to(action, toolbar)

    def get_entry_folder(self, **kwargs_to_entry_folder) -> Path:
        return get_set_config_dir('waveforms')

    def save_entries(self, entry_path: Path = None):
        """Write the waveforms of the channels of the designer"""
        if entry_path is None:
            entry_path = self.entry_filepath
        content = {'version': FORMAT_VERSION,
                   'channels': [waveform.to_dict() for waveform in self.designer.channel_waveforms()]}
        entry_path.write_text(toml.dumps(content))

    def read_entry(self, entry_path: Path) -> list[dict]:
        """The description of the waveforms of an entry, refusing the files of an unknown version"""
        content = toml.loads(Path(entry_path).read_text())
        if content.get('version') != FORMAT_VERSION:
            raise ValueError(f'{Path(entry_path).name}: waveform file of version {content.get("version")}, '
                             f'only version {FORMAT_VERSION} is known')
        return content['channels']

    def can_execute_entry(self) -> bool:
        return self.designer is not None

    def _update_entry(self, entry_path: Path):
        """Set the waveforms of the entry in the channels of the designer"""
        try:
            self.designer.load_channels(self.read_entry(entry_path))
        except (ValueError, KeyError, OSError) as e:
            logger.error(f'Cannot load the waveforms of {Path(entry_path).name}: {e}')

    def _execute_entry(self, entry_path: Path = None, **kwargs) -> bool:
        """Executing an entry is loading it in the channels (done when it is updated): the designer sends them"""
        return True
