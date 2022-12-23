import argparse
import configparser
import shlex
import subprocess
import sys
from collections import OrderedDict
from os import getcwd, makedirs
from os.path import normpath, abspath, exists, expandvars
from typing import List, Dict, Optional


class Host(object):
    def __init__(self, ref_name, host, user, port):
        # type: (str, str, Optional[str], Optional[int]) -> None
        self.ref_name = ref_name
        self.host = host
        self.user = user
        self.port = port


class Folder(object):
    def __init__(self, ref_name, src, dst, host, upload, rsync_args, exclude, exclude_from, work_dir, enabled):
        # type: (str, str, str, Optional[Host], bool, str, List[str], List[str], str, bool) -> None
        self.ref_name = ref_name
        self.src = src
        self.dst = dst
        self.host = host
        self.upload = upload
        self.rsync_args = rsync_args
        self.exclude = exclude
        self.exclude_from = exclude_from
        self.work_dir = work_dir
        self.enabled = enabled


class Config(object):
    config_path = None  # type: str
    hosts = OrderedDict()  # type: Dict[str, Host]
    folders = OrderedDict()  # type: Dict[str, Folder]
    global_rsync_args = None  # type: str


class EnvInterpolation(configparser.BasicInterpolation):
    """Interpolation which expands environment variables in values."""

    def before_get(self, parser, section, option, value, defaults):
        value = super().before_get(parser, section, option, value, defaults)
        return expandvars(value)


class EasyRsync(object):
    HOST_SECTION_NAME = 'host_'
    FOLDER_SECTION_NAME = 'folder_'

    def run(self):
        runtime_config = self.gen_config()

        # iterate folders
        for folder_ref_name, folder in runtime_config.folders.items():
            if not folder.enabled:
                print('Section {} is disabled, skipping rsync execution'.format(folder_ref_name), file=sys.stderr)
                continue
            print('Starting rsync for Section {}'.format(folder_ref_name), file=sys.stderr)
            if self.rsync_folder(folder, runtime_config):
                print('rsync for Section {} finished successfully'.format(folder_ref_name), file=sys.stderr)
            else:
                print('rsync for Section {} finished with errors'.format(folder_ref_name), file=sys.stderr)

    def gen_config(self):
        # type: () -> Config
        config = self.args_config()
        config = self.ini_config(config)
        return config

    # noinspection PyMethodMayBeStatic
    def args_config(self):
        # type: () -> Config
        argparser = argparse.ArgumentParser(prog='easy_rsync',
                                            description='Helper program to spawn multiple rsync-instances based on a '
                                                        'given config file.')
        argparser.add_argument('config')

        namespace, rsync_args = argparser.parse_known_args(sys.argv[1:])
        config = Config()

        config.config_path = namespace.config
        config.global_rsync_args = ' '.join(shlex.quote(arg) for arg in rsync_args)

        return config

    def ini_config(self, config):
        # type: (Config) -> Config
        parser = configparser.ConfigParser(interpolation=EnvInterpolation(),
                                           converters={'list': lambda x: [i.strip() for i in x.split(',')]}
                                           )
        parser.read(config.config_path)

        # parse hosts into config
        for section in parser.sections():
            if not section.lower().startswith(self.HOST_SECTION_NAME):
                continue
            if not parser.has_option(section, 'host'):
                print("Option '{}' missing in Section '{}'".format('host', section), file=sys.stderr)
                continue
            if not parser.has_option(section, 'user'):
                print("Option '{}' missing in Section '{}'".format('user', section), file=sys.stderr)
                continue
            ref_name = parser.get(section, 'ref_name', fallback=section[len(self.HOST_SECTION_NAME):])
            port = parser.getint(section, 'port', fallback=None)
            host = Host(ref_name=ref_name,
                        host=parser.get(section, 'host'),
                        user=parser.get(section, 'user', fallback=None),
                        port=port)
            config.hosts[ref_name] = host

        # parse folders into config, depends on hosts
        for section in parser.sections():
            if not section.lower().startswith(self.FOLDER_SECTION_NAME):
                continue
            if not parser.has_option(section, 'src'):
                print("Option '{}' missing in Section '{}'".format('src', section), file=sys.stderr)
                continue
            if not parser.has_option(section, 'dst'):
                print("Option '{}' missing in Section '{}'".format('dst', section), file=sys.stderr)
                continue
            if parser.has_option(section, 'host'):
                if not parser.has_option(section, 'direction'):
                    print("Option '{}' missing in Section '{}'".format('direction', section), file=sys.stderr)
                    continue
                host_ref_name = parser.get(section, 'host')
                if host_ref_name not in config.hosts:
                    print("Option '{}' in Section '{}' uses an unknown Host '{}'".format(
                        'host', section, host_ref_name), file=sys.stderr)
                    continue
                else:
                    host = config.hosts[host_ref_name]
            else:
                host = None

            if host is None:
                upload = True
            elif parser.get(section, 'direction').lower() in ('u', 'up', 'upload'):
                upload = True
            elif parser.get(section, 'direction').lower() in ('d', 'down', 'download'):
                upload = False
            elif host is not None:
                print("Option '{}' in Section '{}' is not one of <u, up, upload, d, down, download>".format(
                    'direction', section),
                    file=sys.stderr)
                continue
            else:
                raise NotImplementedError

            if parser.has_option(section, 'rsync_args'):
                rsync_args = parser.get(section, 'rsync_args')
            else:
                rsync_args = ''
            if parser.has_option(section, 'exclude'):
                exclude = parser.getlist(section, 'exclude')
            else:
                exclude = []
            if parser.has_option(section, 'exclude_file'):
                exclude_from = []
                for exclude_file_name in parser.getlist(section, 'exclude_file'):
                    if not exists(exclude_file_name):
                        print('Skipping not existing exclude_from File {} in Section {}'.format(
                            exclude_file_name, section), file=sys.stderr)
                        continue
                    else:
                        exclude_from.append(exclude_file_name)
            else:
                exclude_from = []

            work_dir = abspath(normpath(parser.get(section, 'work_dir', fallback=getcwd())))

            ref_name = section[len(self.FOLDER_SECTION_NAME):]

            enabled = parser.getboolean(section, 'enabled', fallback=True)

            folder = Folder(ref_name=ref_name,
                            src=parser.get(section, 'src'),
                            dst=parser.get(section, 'dst'),
                            host=host,
                            upload=upload,
                            rsync_args=rsync_args,
                            exclude=exclude,
                            exclude_from=exclude_from,
                            work_dir=work_dir,
                            enabled=enabled)
            config.folders[ref_name] = folder

        # print error for all other sections
        for section in parser.sections():
            if not section.lower().startswith((self.HOST_SECTION_NAME, self.FOLDER_SECTION_NAME)):
                print("Unknown Section '{}'".format(section), file=sys.stderr)

        return config

    # noinspection PyMethodMayBeStatic
    def rsync_folder(self, folder, runtime_config):
        # type: (Folder, Config) -> bool
        if folder.host:
            if folder.host.port is None:
                ssh_settings = "-e 'ssh'"
            else:
                ssh_settings = "-e 'ssh -p {}'".format(folder.host.port)
            if folder.host.user:
                ssh_prefix = '{user}@{host}:'.format(user=folder.host.user, host=folder.host.host)
            else:
                ssh_prefix = '{host}:'.format(host=folder.host.host)
        else:
            ssh_settings = ''
            ssh_prefix = ''

        if folder.exclude:
            exclude_args = ' '.join('--exclude={path}'.format(path=path) for path in folder.exclude)
        else:
            exclude_args = ''
        if folder.exclude_from:
            exclude_from_args = ' '.join('--exclude-from={path}'.format(path=path) for path in folder.exclude_from)
        else:
            exclude_from_args = ''

        global_rsync_args = runtime_config.global_rsync_args
        rsync_args = '--rsync-path="mkdir -p {} && rsync" -r'.format(folder.dst)
        if folder.rsync_args:
            rsync_args += ' ' + folder.rsync_args

        if folder.upload:
            src_arg = folder.src
            dst_arg = ssh_prefix + folder.dst
        else:
            src_arg = ssh_prefix + folder.src
            dst_arg = folder.dst
            makedirs(dst_arg, exist_ok=True)

        arguments_list = [arguments for arguments in (ssh_settings, exclude_args, exclude_from_args, global_rsync_args,
                                                      rsync_args, src_arg, dst_arg)
                          if arguments]
        command = 'rsync ' + ' '.join(arguments_list)
        print('using rsync command:', command, file=sys.stderr)

        rsync_subprocess = subprocess.Popen(args=command, shell=True, cwd=folder.work_dir)
        rsync_subprocess.wait()

        return rsync_subprocess.returncode == 0


if __name__ == "__main__":
    app = EasyRsync()
    app.run()
