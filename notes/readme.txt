To browse client source code:

    https://sourceforge.net/p/crossfire/code/HEAD/tree/client/trunk/

Basically the only reference guide I've found:

    http://wiki.metalforge.net/doku.php/client_side_scripting:client_scripting_interface-basic_howto

Though TBH, at this point the easiest way for me to figure out how the
scripting interface works is by reading the relevant parts of the client source
code :thinking:... basically see common/script.c.

Misc notes:
  - Possibly "watch stat hp" doesn't work? You might need to just request it
    periodically...
      - "watch stat"/"watch stats" do seem to work, but they're a little
        spammy... mostly you just get a lot of "watch stats food".
      - Okay, "watch" actually just gives you (almost) raw messages from the
        server. You can watch for basically any type of thing the server sends,
        and in most cases you get it exactly as the server sends it (main
        exception is that stat updates are split up into individual messages).
        But the filtering seems a little janky; I'm not sure if it works with
        more than 1 word to specify the type of thing to watch for. Or maybe
        it's exactly that splitting up of stat messages that's why "watch stats
        hp" doesn't work -- because that's not how it actually comes from the
        server.
  - You can "request player" to get the player's tag and name+title.

Item information:
  - See common/script.c:1610, comment above function script_send_item.
  - Basically whenever you request items, each comes through as something like:
        request items inv <tag> <num> <weight> <flags> <type> <name>
    where...
      - tag is the item's tag; see below for ways you can use this.
      - num is the size of the pile.
      - weight is the item's weight, as an integer number of grams. (Normally
        item weights are displayed in kilograms; this is scaled up by 1000.)
          - Fun fact -- apparently the client tracks the weight as a float, in
            kilograms, and then translates that to an integer for the sake of
            scripts. :thinking:
      - flags is a bitmask:
            0x0200  512     unidentified
            0x0100  256     magical
            0x0080  128     cursed
            0x0040   64     damned
            0x0020   32     unpaid
            0x0010   16     locked
            0x0008    8     applied
            0x0004    4     open
            0x0002    2     was_open
            0x0001    1     inv_updated
        I don't know what all of these mean, though some of them seem obvious
        enough.
      - type (I'm pretty sure) is the client_type from the archetypes file.
        It's just an integer value that controls how items sort in the client's
        inventory list. Could be useful if you're trying to write a script to
        autosort stuff in an apartment/guild, since it basically gives you
        information at the level of "X is a cloak. Y is a wand. Z is a coin."
          - Note the archetypes file also has a "type" field for each entry,
            which is something totally different. I'm not actually sure what
            that is. Under no circumstances confuse the archetype type with the
            client_type (called simply "type" by the client), except under
            confusing circumstances.
      - name is the human-readable name of the object, which will often contain
        internal spaces.
  - I think _watching_ for changes to items might be a lost cause. The messages
    for when you drop or pick up an item come through as something like:
        watch item2 ## bytes unparsed: 00 00 0c 6f [...]
    In other words, a bunch of totally unparsed bytes encoded in hex.

Manipulating items directly:
  - Use "monitor" then click on things to see the syntax.
  - Basically there are special commands that you can issue that look like
    "issue <command>" without the <count> <must_send>.
  - To pick up, drop, or move an item into a container, use "move". Syntax is:
            issue move <dest_tag> <tag_of_thing_to_move> <count>
      - To pick up an item, <dest_tag> is the player's tag, obtainable via
        "request player".
      - To drop an item, <dest_tag> is 0.
      - To move an item into a container, <dest_tag> is the tag of the
        container. The container might have to be open, and I'm not quite sure
        how this works when the container is on the ground under you (ex: a
        cauldron).
    *** WARNING! This will ignore whether the item is locked! Make sure to
        check this yourself first. ***
  - To apply an item, use "issue apply <tag>".
      - It looks like "-a" and "-u" don't work here, at least not in that form.
  - To mark an item, "issue mark <tag>".
  - There's also a syntax to lock/unlock items. It seems to be:
        lock:   issue lock 1 <tag>
        unlock: issue lock 0 <tag>
    I think in the actual client-server protocol, the {0, 1} is actually a
    single byte, either '\x00' or '\x01'. When your script does an "issue
    lock", the client translates it, but "monitor" does not, so if you monitor
    lock and unlock commands, you'll just see garbage.



If you want local information about items from a server installation, useful
files are in:

    /usr/share/games/crossfire

(at least on Ubuntu-like systems). A couple of particularly useful files:

    /usr/share/games/crossfire/formulae   -- alchemical formulae
    /usr/share/games/crossfire/archetypes -- item archetypes

