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
  - You can "request player" to get the player's tag and name+title.
