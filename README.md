pif, which could mean Photos Into Flickr
========================================

Is [Flickr](http://flickr.com/) a hard drive in the sky for you?

Got photos everywhere and not sure which are on the web and which are
languishing in digital obscurity?

Point `pif` at 'em; a single JPEG, or a whole directory. It don't matter!
`pif` will chat with Flickr and line-up the stragglers.

Then, if you want to upload them, `pif` can do that too.


How does it work, salesman?
---------------------------

Well, let me tell you!

 1. Have some photos!

     Do you have some photos?

        $ ls
        croppedDSC00375.JPG
        DSC00381.JPG
        DSC00404.JPG
        IMG_0283.JPG
        IMG_0486.JPG
        IMG_3405r.jpg
        smaller.jpg

    I guess you do.

 2. Run `pif`!

        $ pif
        $

    Uh. I meant...

 3. Use, like, the options, man!

        $ pif --help
        Usage: pif [options] <filename ...>

        Options:
          -h, --help     show this help message and exit
          -v, --verbose  increase verbosity
          -f, --force    force file(s) to be uploaded
          -m, --mark     mark file(s) as uploaded
          -n, --dry-run  do not upload file(s)

    Yes. *That!* That is what I meant!

        $ pif --verbose --dry-run .
        INFO:pif.ui.console: Would have uploaded croppedDSC00375.JPG
        INFO:pif.ui.console: Would have uploaded DSC00381.JPG
        INFO:pif.ui.console: Would have uploaded DSC00404.JPG
        INFO:pif.ui.console: IMG_0283.JPG already uploaded, skipping (use --force to upload)
        INFO:pif.ui.console: IMG_0486.JPG already uploaded, skipping (use --force to upload)
        INFO:pif.ui.console: Would have uploaded IMG_3405r.jpg
        INFO:pif.ui.console: Would have uploaded smaller.jpg

    See those photos already uploaded? **THEY ARE ON FLICKR.**

 4. But, uh, what about those bad photos...

        $ pif --verbose --mark croppedDSC00375.JPG IMG_3405r.jpg smaller.jpg
        INFO:pif.ui.console: croppedDSC00375.JPG marked as already uploaded
        INFO:pif.ui.console: IMG_3405r.jpg  marked as already uploaded
        INFO:pif.ui.console: smaller.jpg marked as already uploaded

    What about them?

        $ pif --verbose .
        INFO:pif.ui.console: Uploaded DSC00381.JPG
        INFO:pif.ui.console: Uploaded DSC00404.JPG

    All done. Believe me?

        $ pif --verbose .
        INFO:pif.ui.console:Loading updates from Flickr... (1 / 1)
        INFO:pif.ui.console:Indexing photos on Flickr... (1 / 2)
        INFO:pif.ui.console:Indexing photos on Flickr... (2 / 2)
        $

    **SNAP!** That was `pif`, figuring out your photos were well and truly
    uploaded. No half-assery here!

That was really. Really. REALLY complex!
----------------------------------------

OK.

        $ pif-gtk .

Debian / Ubuntu Package Requirements:
-------------------------------------

        $ aptitude install python-gobject python-gtk2 python-imaging \
                           python-setuptools python-minimock python-nose
