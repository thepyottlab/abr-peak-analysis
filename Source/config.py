"""Encapuslate a Default Values Object and Config File"""
 
from inspect import getmembers
import configparser
import os
import sys
 
class DefaultValueHolder(object):
    """Intended for use with wxConfig (or maybe _winreg) to set up and/or get
       registry key names and values. Name attrs as default*. "default"
       will be stripped of when reading and writing to the config file.
       You may not use the name varDict as one of the variable names."""
 
    def __init__(self, appName, grpName):
        """Open or create the application key"""
        self.appName = appName
        self.grpName = grpName  # if the key or group doesn't exit, it will be created
        self.config = configparser.ConfigParser()
        if sys.platform == 'win32':
            self.configpath = os.environ['ALLUSERSPROFILE'] + '\\' + appName + ".ini"
        else:
            home = os.path.expanduser("~")
            self.configpath = os.path.join(
                home,
                "Library",
                "Preferences",
                f"{appName} Preferences"
            )
        
 
    def __getattribute__(self, name):
        try:
            return object.__getattribute__(self, "default%s" %name)
        except AttributeError:
            return object.__getattribute__(self, name)
 
    def GetVariables(self):
        return [{"name":var[0][7:], "value":var[1], "type":type(var[1])}
                for var in getmembers(self) if var[0].startswith('default')]
 
    def SetVariables(self, varDict={}, **kwargs):
        kwargs.update(varDict)
        for name, value in kwargs.items():
            setattr(self, "default%s" %name, value)
 
    def InitFromConfig(self):
        config = self.config
        group = self.grpName
 
        if os.path.isfile(self.configpath):
            self.config.read(self.configpath)

        if not config.has_section(group):
            self.config.add_section(self.grpName)
            self.WriteConfigSection(group)
 
        else:
            for var in self.GetVariables():
                name = var['name']
                if config.has_option(group, name):
                    value = self.ReadConfig(name, var['type'])
                    self.SetVariables({name:value})
                else:
                    self.WriteConfig(name, var['value'], var['type'])
 
    def WriteConfigSection(self, section):
        for var in self.GetVariables():
            self.WriteConfig(var['name'], var['value'], var['type'])
 
    def UpdateConfig(self):
        if os.path.isfile(self.configpath):
            self.config.read(self.configpath)

        if not self.config.has_section(self.grpName):
            self.config.add_section(self.grpName)
        
        self.WriteConfigSection(self.grpName)
        
        with open(self.configpath, 'w') as configfile:
            self.config.write(configfile)
            configfile.close()       
    
    def ReadConfig(self, name, type):
        value = None
        if type == str:
            value = self.config.get(self.grpName, name)
        elif type == int:
            value = self.config.getint(self.grpName, name)
        elif type == bool:
            value = self.config.getboolean(self.grpName, name)
        elif type == float:
            value = self.config.getfloat(self.grpName, name)
        return value
 
    def WriteConfig(self, name, value, type):
        self.config.set(self.grpName, name, str(value))
 
if __name__ == "__main__":
    test = DefaultValueHolder("HETAP Pro 2.00", "Database")
    test.SetVariables(UserName = "peter", Password = "pan", ServerName = "MyServer", database="")
    test.InitFromConfig()
    print(test.UserName)
    test.defaultvar1=77
    print(test.GetVariables())
    #### this also works:
    ## test.defaultUserName = "joe"
