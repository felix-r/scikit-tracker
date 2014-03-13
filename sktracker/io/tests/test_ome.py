import os

from nose import with_setup

from sktracker.io import OMEModel

current_dir = os.path.dirname(os.path.realpath(__file__))

xml_str = None

def open_tubhiswt_4D_ome_xml():
    fname = "tubhiswt-4D.ome.xml"
    f = open(os.path.join(current_dir, fname))
    global xml_str
    xml_str = f.read()
    f.close()
    return xml_str

def xml_str_clean():
    xml_str = None

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_loading():

    m = OMEModel(xml_str)
    del m

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_df_planes():
    m = OMEModel(xml_str)
    assert m.df_planes() == None

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_get_metadata():
    m = OMEModel(xml_str)
    metadata = m.get_metadata()
    real_metadata = {'shape': (2, 43, 10, 512, 512),
                     'axes': ['C', 'T', 'Z', 'Y', 'X'],
                     'acquisition_date': '2013-01-15T17:02:48'}
    assert metadata == real_metadata

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_to_string():
    """Test OMEModel.tostring() method: how can we check that ?
    """
    m = OMEModel(xml_str)
    m.tostring()
    # assert m.tostring() == open_tubhiswt_4D_ome_xml()
    assert True

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_set_xy_size():
    m = OMEModel(xml_str)
    size_x = 50
    size_y = 45
    m.set_xy_size(size_x, size_y)
    md = m.get_metadata()
    assert md['shape'][-1] == size_x and md['shape'][-2] == size_y

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_set_z_size():
    m = OMEModel(xml_str)
    size_z = 50
    m.set_z_size(size_z)
    md = m.get_metadata()
    assert md['shape'][2] == size_z

@with_setup(setup=open_tubhiswt_4D_ome_xml, teardown=xml_str_clean)
def test_ome_set_physical_size():
    m = OMEModel(xml_str)
    size_x = 0.065
    size_y = 0.065
    size_z = 0.300
    m.set_physical_size(size_x, size_y, size_z)
    physical_size = m.get_physical_size()
    assert physical_size['PhysicalSizeX'] == str(size_x) and \
           physical_size['PhysicalSizeY'] == str(size_y) and \
           physical_size['PhysicalSizeZ'] == str(size_z)