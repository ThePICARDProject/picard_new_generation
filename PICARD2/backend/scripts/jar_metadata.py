from zipfile import BadZipFile, ZipFile


def detect_main_class(upload):
    """Read the manifest's main section without extracting or executing the JAR."""
    try:
        with ZipFile(upload) as jar:
            try:
                with jar.open('META-INF/MANIFEST.MF') as manifest:
                    raw = manifest.read(65537)
            except KeyError:
                return None
            if len(raw) > 65536:
                raise ValueError('The JAR manifest is too large to read automatically. Enter a main class override.')

        # Manifest attributes can wrap onto continuation lines starting with a space.
        lines = []
        for line in raw.decode('utf-8').splitlines():
            if not line:
                break  # Later sections describe individual entries, not the application.
            if line.startswith(' ') and lines:
                lines[-1] += line[1:]
            else:
                lines.append(line)
        for line in lines:
            name, separator, value = line.partition(':')
            if separator and name.lower() == 'main-class':
                return value.strip() or None
        return None
    except (BadZipFile, UnicodeDecodeError, RuntimeError, NotImplementedError, EOFError) as error:
        raise ValueError('Unable to read the JAR manifest. Upload a valid JAR or enter a main class override.') from error
    finally:
        upload.seek(0)
