<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="html"/>

    <xsl:template match="form">
      <html>
	<head>
	  <style>
	    body {
	      font-family: sans-serif;
	    }
	    h1 {
	      font-size: 20;
	      margin-bottom: 0px;
	    }
	    h4 {
	      margin-top: 0px;
	      margin-bottom: 0px;
	      font-size: 10;
	    }
	    h2 {
	      margin-top: 5px;
	      margin-bottom: 0px;
	    }
	    h3 {
	      margin-top: 0px;
	    }
	    table.header {
	      width: 600px;
	      
	    }
	    table.form {
	      width: 600px;
	      border-spacing: 0px;
	      border-collapse: collapse;
	    }
	    tr.row td:first-child {
	      border-left: thin solid black;
	    }
	    tr.row td:last-child {
	      border-right: thin solid black;
	    }
	    table.form td {
	      border-top: thin solid black;
	      padding-left: 10px;
	      padding-right: 10px;
	      padding-top: 3px;
	      padding-bottom: 3px;
	    }
	    .underline {
	      text-decoration: underline;
	    }
	    div.element {
	      display: inline;
	    }
	    .subtext {
	      font-size: 60%;
	    }
	    div.choice {
	      display: inline-block;
	      width: 150px;
	      text-align: left;
	    }
	    div.choice-block {
	      text-align: right;
	    }
	    .center-aligned {
	      text-align: center;
	    }
	    .right-aligned {
	      text-align: right;
	    }
	    div.box {
	      border: thin solid black;
	      padding: 10px;
	      width: 300px;
	      margin-left: auto;
	      margin-right: auto;
	    }
	    .title {
	      font-size: 18;
	    }
	    div.multiline {
	      height: 200px;
	    }
	    div.coord {
	      display: inline-block;
	      //width: 120px;
	      text-align: left;
	      margin-left: 20px;
	    }
	    div.coords {
	      text-align: right;
	      display: inline-block;
	    }
	  </style>
	</head>
	<body>
	  <table class="header" align="center">
	    <td width="170"><img src="http://www2.fiu.edu/orgs/w4ehw/images/wx4nhc%20logo.jpg" width="160"/></td>
	    <td width="*">
	      <div class="center-aligned">
		<h1>AMATEUR RADIO STATION - WX4NHC</h1>
		<h4>AT THE</h4>
		<h2>NATIONAL HURRICANE CENTER</h2>
		<span class="underline"><h3>SURFACE WEATHER REPORT</h3></span>
	      </div>
	      <div class="box">
		<span class="title">Hurricane:</span> <xsl:apply-templates select="field[@id='hurricane']"/>
	      </div>
	    </td>
	  </table>

	  <table class="form" cellpadding="0" align="center">
	    <tr class="row">
	      <td colspan="2">
		Reporting Station Callsign: <xsl:apply-templates select="field[@id='callsign']"/>
	      </td>
	    </tr>
	    <tr class="row">
	      <td colspan="2">
		Geographic Location: <xsl:apply-templates select="field[@id='location']"/>
	      </td>
	    </tr>
	    <tr class="row">
	      <td>
		Location: (Latitude/Longitude):
	      </td>
	      <td>
		<div class="coords">
		  <div class="coord">
		    <span class="underline"><xsl:apply-templates select="field[@id='lat']"/></span> North
		  </div>
		  <div class="coord">
		    <span class="underline"><xsl:apply-templates select="field[@id='lon']"/></span> West
		  </div>
		</div>
	      </td>
	    </tr>
	    <tr class="spacer">
	      <td colspan="2">&#160;</td>
	    </tr>
	    <tr class="row">
	      <td>Date: <xsl:apply-templates select="field[@id='date']"/></td>
	      <td class="right-aligned">Time of Observation: <xsl:apply-templates select="field[@id='time']"/> (Z) (GMT)</td>
	    </tr>
	    <tr class="spacer">
	      <td colspan="2">&#160;</td>
	    </tr>
	    <tr class="row">
	      <td>
		Wind Speed: <span class="underline"><xsl:apply-templates select="field[@id='wind']"/></span><br/>
		<span class="subtext">(sustained for one minute)</span>
	      </td>
	      <td>
		<xsl:apply-templates select="field[@id='wind_units']"/>
		<xsl:apply-templates select="field[@id='wind_meas']"/>
	      </td>
	    </tr>
	    <tr class="row">
	      <td>
		Wind Gust: <xsl:apply-templates select="field[@id='wind_gust']"/>
	      </td>
	      <td>
	      </td>
	    </tr>
	    <tr class="row">
	      <td colspan="2">Wind Direction: <xsl:apply-templates select="field[@id='wind_dir']"/></td>
	    </tr>
	    <tr class="spacer">
	      <td colspan="2">&#160;</td>
	    </tr>
	    <tr class="row">
	      <td>
		Barometric Pressure: <xsl:apply-templates select="field[@id='press']"/><br/>
		<span class="subtext">(convert to millibars)</span>
	      </td>
	      <td>
		<xsl:apply-templates select="field[@id='press_units']"/>
	      </td>
	    </tr>
	    <tr class="spacer">
	      <td colspan="2">&#160;</td>
	    </tr>
	    <tr class="row">
	      <td colspan="2">
		Additional Comments:
		<div class="multiline">
		  <xsl:apply-templates select="field[@id='comments']"/>
		</div>
	      </td>
	    </tr>
	    <tr class="spacer">
	      <td colspan="2">&#160;</td>
	    </tr>
	    <tr class="row">
	      <td colspan="2">
		Operator: <xsl:apply-templates select="field[@id='op']"/>
	      </td>
	    </tr>
	    <tr class="spacer">
	      <td>&#160;</td>
	      <td class="right-aligned"><span class="subtext">Digital version generated by D-RATS</span></td>
	    </tr>
	  </table>
	</body>
      </html>
    </xsl:template>

    <xsl:template name="field">
      <xsl:text>No</xsl:text>
    </xsl:template>

    <xsl:template name="header-field">
      <xsl:param name="caption"/>
      <xsl:param name="value"/>
      <table class="element">
	<tr><td>
	    <span class="hfield-caption">
	      <xsl:value-of select="$caption"/>
	    </span>
	    <xsl:text>   </xsl:text>
	    <span class="field-content">
	      <xsl:value-of select="$value"/>
	    </span>
	</td></tr>
      </table>
    </xsl:template>

    <xsl:template match="choice">
      <xsl:choose>
	<xsl:when test="@set='y'">
	  <input type="checkbox" checked="checked"/>
	</xsl:when>
	<xsl:otherwise>
	  <input type="checkbox"/>
	</xsl:otherwise>
      </xsl:choose>
      <xsl:value-of select="."/>
    </xsl:template>

    <xsl:template match="entry">
      <xsl:choose>
	<xsl:when test="@type = 'choice'">
	  <div class="choice-block">
	    <xsl:for-each select="choice[(position() mod 2) = 1]">
	      <div class="choice"><xsl:apply-templates select="."/></div>
	      <div class="choice"><xsl:apply-templates select="following-sibling::choice[position() = 1]"/></div>
	    </xsl:for-each>
	  </div>
	</xsl:when>
	<xsl:when test="@type = 'multiselect'">
	  <table width="100%">
	      <xsl:for-each select="choice[(position() mod 4) = 1]">
		<tr>
		  <td class="element"><xsl:apply-templates select="."/></td>
		  <td class="element"><xsl:apply-templates select="following-sibling::choice[position() = 1]"/></td>
		  <td class="element"><xsl:apply-templates select="following-sibling::choice[position() = 2]"/></td>
		  <td class="element"><xsl:apply-templates select="following-sibling::choice[position() = 3]"/></td>
		</tr>
	      </xsl:for-each>
	  </table>
	</xsl:when>
	<xsl:when test="@type='toggle'">
	  <xsl:choose>
	    <xsl:when test=". = 'True'">
	      <input type="checkbox" checked="checked"/>
	      <xsl:text>YES   </xsl:text>
	      <input type="checkbox"/>
	      <xsl:text> NO</xsl:text>
	    </xsl:when>
	    <xsl:otherwise>
	      <input type="checkbox"/>
	      <xsl:text>YES   </xsl:text>
	      <input type="checkbox" checked="checked"/>
	      <xsl:text> NO</xsl:text>
	    </xsl:otherwise>
	  </xsl:choose>
	</xsl:when>
	<xsl:otherwise>
	  <xsl:value-of select="."/>
	</xsl:otherwise>
      </xsl:choose>
    </xsl:template>

    <xsl:template match="field">
      <xsl:variable name="element_class">
	<xsl:choose>
	  <xsl:when test="entry[@type='multiselect']">
	    <xsl:text>bigelement</xsl:text>
	  </xsl:when>
	  <xsl:otherwise>
	    <xsl:text>element</xsl:text>
	  </xsl:otherwise>
	</xsl:choose>
      </xsl:variable>

      <div class="{$element_class}">
	<span class="field-caption">
	  <!--<xsl:value-of select="caption"/>-->
	</span>
	<xsl:text>   </xsl:text>
	<span class="field-content">
	  <xsl:apply-templates select="entry"/>
	</span>
      </div>
    </xsl:template>



</xsl:stylesheet>
