def ecoEDA_setup():
    #set values of ecoEDA_config.json
    # TO DO: create a nice UI to import data

    shell.write("Open ecoEDA_config.json in your ecoEDA directory and add the relevant information")
    shell.write(ecoEDA_dir + "ecoEDA_config.json")


def restart_ecoEDA():
    shell.run("server.shutdown()")
    shell.run("server.server_close()")
    shell.run("ser_thread.join()")
    shell.runfile(ecoEDA_dir + "PyShell_eeschema_startup.py")
    shell.write("ecoEDA restarted")


if os.name == 'nt':
    shell.run('cd ..')
    shell.run('cd(\"' + repr(ecoEDA_dir)[1:-3] + '\")')
else:
    shell.run('cd ..')
    shell.run("cd " + ecoEDA_dir)

#shell.clear() #uncomment for more aesthetic ecoEDA experience with pyshell
shell.write("ecoEDA is set up! Make sure to run ecoEDA scripts locally to get real-time suggestions.")
shell.write("If you need to pull up the main menu again, type 'main_menu.Show()' here and press enter.")
