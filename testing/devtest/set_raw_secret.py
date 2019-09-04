# load up the simulator w/ indicated test master key
import tcc, main
from sim_settings import sim_defaults
import stash, chains
from h import b2a_hex
from main import settings, pa
from stash import SecretStash, SensitiveValues
from utils import xfp2str

rs = main.RAW_SECRET 
print("New raw secret: %s" % b2a_hex(rs))

if 1:
    settings.current = sim_defaults
    settings.overrides.clear()
    settings.set('chain', 'XTN')

    pa.change(new_secret=rs)
    pa.new_main_secret(rs)

    print("New key in effect: %s" % settings.get('xpub', 'MISSING'))
    print("Fingerprint: %s" % xfp2str(settings.get('xfp', 0)))

